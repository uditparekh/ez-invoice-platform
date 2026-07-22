"""Phase B AI routing: external AI for training/unseen formats, never trusted.

Also covers the activation-pass config fix: SIFTENTRY_AI_MODEL must reach the
live app config via AiExtractorConfig.from_settings (previously only
from_environment read it, so deployed Groq calls fell back to gpt-4o-mini).
"""

import io
import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from siftentry_app.backend.ai_parser import AiExtractorConfig

from .test_ai_anthropic import make_invoice_pdf


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_from_settings_reads_model_env(monkeypatch):
    """The deployed path (from_settings) must honor SIFTENTRY_AI_MODEL."""
    monkeypatch.setenv("SIFTENTRY_AI_API_KEY", "gsk-test-not-a-real-key")
    monkeypatch.setenv("SIFTENTRY_AI_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("SIFTENTRY_AI_MODEL", "llama-3.3-70b-versatile")
    settings = SimpleNamespace(
        ai_provider="groq",
        ai_extractor_url="",
        ai_extractor_token="",
        ai_timeout_seconds=8.0,
        ai_max_payload_chars=120_000,
        ai_policy="review_only",
    )
    config = AiExtractorConfig.from_settings(settings)
    assert config.provider == "openai_compatible"  # groq alias
    assert config.model == "llama-3.3-70b-versatile"
    assert config.base_url == "https://api.groq.com/openai/v1"
    assert config.live_provider is True


@pytest.fixture()
def live_ai_client(tmp_path, monkeypatch):
    """App with a live (fake) Groq-style provider configured, plus a call log."""
    db = tmp_path / "routing.db"
    monkeypatch.setenv("EZ_API_DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setenv("EZ_API_ALLOW_DEV_BOOTSTRAP", "true")
    monkeypatch.setenv("EZ_API_UPLOAD_DIRECTORY", str(tmp_path / "uploads"))
    monkeypatch.setenv("SIFTENTRY_AI_PROVIDER", "groq")
    monkeypatch.setenv("SIFTENTRY_AI_API_KEY", "gsk-test-not-a-real-key")
    monkeypatch.setenv("SIFTENTRY_AI_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("SIFTENTRY_AI_MODEL", "llama-3.3-70b-versatile")

    calls: list = []
    envelope = json.dumps(
        {
            "model": "llama-3.3-70b-versatile",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "fields": {
                                    "invoice_number": {
                                        "value": "2620002662",
                                        "confidence": 0.97,
                                        "reason": "header",
                                    }
                                }
                            }
                        )
                    }
                }
            ],
        }
    ).encode("utf-8")

    def fake_urlopen(req, timeout=0):
        calls.append(req.full_url)
        assert req.full_url == "https://api.groq.com/openai/v1/chat/completions"
        body = json.loads(req.data.decode("utf-8"))
        assert body["model"] == "llama-3.3-70b-versatile"
        return FakeResponse(envelope)

    monkeypatch.setattr(
        "siftentry_app.backend.openai_extractor.urlrequest.urlopen", fake_urlopen
    )

    from siftentry_app.backend.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client, calls


def _bootstrap(client: TestClient):
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={
            "email": f"owner-{uuid.uuid4().hex[:8]}@routing.test",
            "password": "long-password-123456",
            "full_name": "Owner",
            "organization_name": "Routing Org",
            "legal_names": [],
            "default_currency": "INR",
        },
    )
    assert response.status_code in (200, 201), response.text
    payload = response.json()
    return (
        {"Authorization": f"Bearer {payload['access_token']}"},
        payload["user"]["memberships"][0]["organization_id"],
    )


def _upload(client, headers, org_id, filename):
    response = client.post(
        f"/api/v1/invoices/upload?organization_id={org_id}",
        files={"file": (filename, make_invoice_pdf(), "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_auto_routing_gates_ai_by_format_status(live_ai_client):
    client, calls = live_ai_client
    headers, org_id = _bootstrap(client)

    # 1) Unseen supplier format in `auto` mode -> external AI runs.
    first = _upload(client, headers, org_id, "unseen-format.pdf")
    assert len(calls) == 1
    document = first["raw_payload"]["INVOICE"]["DOCUMENT"]
    assert document["AI/OCR PROVIDER"] == "openai_compatible"
    assert document["AI/OCR MODEL"] == "llama-3.3-70b-versatile"
    assert document["AI/OCR TRIGGER"] == "training_format"
    assert document["AI/OCR SUGGESTIONS"]["invoice_number"]["value"] == "2620002662"

    supplier_name = first["supplier"]["name"]
    supplier_tax_id = first["supplier"].get("tax_id", "") or ""
    assert supplier_name, "parser must extract a supplier for the gate to key on"

    # 2) Graduate the format: five clean approvals -> trusted.
    repository = client.app.state.repository
    for index in range(5):
        outcome = repository.record_supplier_format_outcome(
            organization_id=org_id,
            supplier_name=supplier_name,
            supplier_tax_id=supplier_tax_id,
            invoice_id=f"seed-{index}",
            had_corrections=False,
        )
    assert outcome["status"] == "trusted"

    # 3) Trusted format -> deterministic only, zero provider calls.
    second = _upload(client, headers, org_id, "trusted-format.pdf")
    assert len(calls) == 1  # unchanged
    trusted_document = second["raw_payload"]["INVOICE"]["DOCUMENT"]
    assert "AI/OCR TRIGGER" not in trusted_document
    assert "AI/OCR SUGGESTIONS" not in trusted_document

    # 4) A correction demotes to training -> the gate re-opens.
    demoted = repository.record_supplier_format_outcome(
        organization_id=org_id,
        supplier_name=supplier_name,
        supplier_tax_id=supplier_tax_id,
        invoice_id="seed-correction",
        had_corrections=True,
    )
    assert demoted["status"] == "training"
    third = _upload(client, headers, org_id, "demoted-format.pdf")
    assert len(calls) == 2
    assert third["raw_payload"]["INVOICE"]["DOCUMENT"]["AI/OCR TRIGGER"] == (
        "training_format"
    )


def test_review_surfaces_ai_suggestions(live_ai_client):
    """After an auto-gated AI parse, the review endpoint must show the AI's
    output: a pinned summary insight and per-field annotations reviewers can
    see (and Udit can screenshot for grading)."""
    client, calls = live_ai_client
    headers, org_id = _bootstrap(client)
    invoice = _upload(client, headers, org_id, "review-surface.pdf")
    assert len(calls) == 1

    review = client.get(f"/api/v1/invoices/{invoice['id']}/review", headers=headers)
    assert review.status_code == 200, review.text
    body = review.json()

    insight = body["insights"][0]  # pinned first, survives the UI's 3-card cap
    assert insight["title"] == "AI extraction ran"
    assert "openai_compatible" in insight["detail"]
    assert "llama-3.3-70b-versatile" in insight["detail"]
    assert "training format" in insight["detail"]
    assert "field suggestion" in insight["action"]

    number_field = next(
        field for field in body["fields"] if field["field_path"] == "invoice_number"
    )
    # Fake provider suggests the same number the parser found -> agreement note.
    assert number_field["value"] == "2620002662"
    assert "AI agrees" in number_field["suggestion"]


def test_disagreement_bumps_field_to_review_without_patch_leak():
    """When AI disagrees, the field is flagged with the AI's value — but the
    auto-apply suggested_patch must stay AI-free (review_only policy)."""
    from siftentry_app.backend.domain import legacy_payload_to_invoice
    from siftentry_app.backend.models import Invoice
    from siftentry_app.backend.review_service import build_invoice_review

    from .test_domain import sample_legacy_payload

    payload = sample_legacy_payload()
    document = payload.setdefault("INVOICE", payload).setdefault("DOCUMENT", {})
    document["AI/OCR PROVIDER"] = "openai_compatible"
    document["AI/OCR MODEL"] = "llama-3.3-70b-versatile"
    document["AI/OCR TRIGGER"] = "training_format"
    document["AI/OCR SUGGESTIONS"] = {
        "invoice_number": {
            "value": "DIFFERENT-123",
            "confidence": 0.91,
            "reason": "top-right header",
        }
    }
    create = legacy_payload_to_invoice(
        payload, organization_id="org-x", source_file="unit.pdf"
    )
    invoice = Invoice(
        id="inv-x",
        **create.model_dump(exclude={"organization_id"}),
        organization_id="org-x",
        created_at="2026-07-22T00:00:00Z",
        updated_at="2026-07-22T00:00:00Z",
    )
    review = build_invoice_review(invoice)

    number_field = next(
        field for field in review.fields if field.field_path == "invoice_number"
    )
    assert "DIFFERENT-123" in number_field.issue
    assert "91%" in number_field.issue
    assert number_field.severity.value in ("review", "error")
    assert review.insights[0].title == "AI extraction ran"
    assert "1 differ" in review.insights[0].action
    assert "invoice_number" not in review.suggested_patch


def test_explicit_ai_mode_still_works_without_gate(live_ai_client):
    """parser_mode=ai bypasses the gate entirely (manual/API-driven runs)."""
    client, calls = live_ai_client
    headers, org_id = _bootstrap(client)
    response = client.post(
        f"/api/v1/invoices/upload?organization_id={org_id}&parser_mode=ai",
        files={"file": ("manual-ai.pdf", make_invoice_pdf(), "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert len(calls) == 1
    document = response.json()["raw_payload"]["INVOICE"]["DOCUMENT"]
    assert document["AI/OCR PROVIDER"] == "openai_compatible"
    assert "AI/OCR TRIGGER" not in document  # explicit mode, not auto-gated
