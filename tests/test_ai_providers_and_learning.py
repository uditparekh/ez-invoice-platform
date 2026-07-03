"""Tests for the provider-agnostic AI layer + learning export/import (Step 11 revised)."""

import io
import json
from pathlib import Path

from siftentry_app.backend.ai_parser import (
    AiExtractorConfig,
    _normalize_provider,
    request_external_ai_suggestions,
)

from .test_api import authorization, bootstrap, make_client, organization_id
from .test_ai_anthropic import make_invoice_pdf


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_default_is_off_no_external_calls():
    """Without explicit provider+key env, extraction is local-only and free."""
    config = AiExtractorConfig()  # defaults
    assert config.provider == "profile_context"
    assert config.live_provider is False
    result = request_external_ai_suggestions({"INVOICE": {}}, {}, config=config)
    assert result["provider"] == "profile_context"
    assert result["suggestions"] == {}  # no external call ever attempted


def test_provider_normalization_covers_the_market():
    for alias in ["openai", "gpt", "gemini", "groq", "deepseek", "openrouter", "ollama"]:
        assert _normalize_provider(alias) == "openai_compatible"
    assert _normalize_provider("claude") == "anthropic"
    assert _normalize_provider("") == "profile_context"
    assert _normalize_provider("off") == "disabled"


def test_openai_compatible_adapter_roundtrip(monkeypatch):
    """One adapter, many brains: assert the /chat/completions dialect works and
    evidence still comes from the local text layer."""
    pdf_bytes = make_invoice_pdf()
    model_json = {
        "fields": {
            "invoice_number": {"value": "2620002662", "confidence": 0.97, "reason": "header"}
        }
    }
    fake_envelope = json.dumps(
        {
            "model": "llama3.1:8b",
            "choices": [{"message": {"content": json.dumps(model_json)}}],
        }
    ).encode("utf-8")

    def fake_urlopen(req, timeout=0):
        assert req.full_url == "http://127.0.0.1:11434/v1/chat/completions"  # Ollama!
        sent = json.loads(req.data.decode("utf-8"))
        assert sent["messages"][0]["role"] == "system"
        user_payload = json.loads(sent["messages"][1]["content"])
        assert user_payload["client_context"]["profile_name"] == "Neel Enterprise"
        return FakeResponse(fake_envelope)

    import siftentry_app.backend.openai_extractor as extractor

    monkeypatch.setattr(extractor.urlrequest, "urlopen", fake_urlopen)

    config = AiExtractorConfig(
        provider="openai_compatible",
        api_key="local",
        base_url="http://127.0.0.1:11434/v1",
        model="llama3.1:8b",
    )
    result = request_external_ai_suggestions(
        {"INVOICE": {}},
        {"profile_name": "Neel Enterprise"},
        config=config,
        document_text="Invoice No: 2620002662",
        pdf_bytes=pdf_bytes,
    )
    assert result["provider"] == "openai_compatible"
    assert result["model"] == "llama3.1:8b"
    assert result["suggestions"]["invoice_number"]["value"] == "2620002662"
    assert result["suggestions"]["invoice_number"]["evidence"]["page"] == 1


def test_learning_export_import_roundtrip(tmp_path: Path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        headers = authorization(tokens)

        # Seed learnable state: org settings + a client profile with instructions.
        client.put(
            f"/api/v1/organizations/{org_id}/settings",
            json={"default_currency": "INR", "default_country": "IN",
                  "primary_accounting_system": "tally",
                  "data_retention": "review_window",
                  "notifications": {"approvals": True, "failures": True, "digest": False}},
            headers=headers,
        )
        created = client.post(
            f"/api/v1/organizations/{org_id}/client-profiles",
            json={"name": "Neel Enterprise", "accounting_system": "tally",
                  "description": "seed", "is_default": True, "settings": {}},
            headers=headers,
        )
        assert created.status_code in (200, 201)

        # Export the bundle.
        response = client.get(
            f"/api/v1/organizations/{org_id}/learning/export", headers=headers
        )
        assert response.status_code == 200
        bundle = response.json()
        assert bundle["schema_version"] == "siftentry_learning_v1"
        assert bundle["organization_settings"]["default_currency"] == "INR"
        assert any(p["name"] == "Neel Enterprise" for p in bundle["client_profiles"])

        # Import into a SECOND organization: the new brain's starting point.
        second = client.post(
            "/api/v1/organizations",
            json={"name": "Second Practice", "legal_names": [], "default_currency": "USD"},
            headers=headers,
        )
        assert second.status_code in (200, 201)
        refreshed = client.get("/api/v1/auth/me", headers=headers).json()
        second_id = next(
            m["organization_id"] for m in refreshed["memberships"]
            if m["organization_name"] == "Second Practice"
        )
        imported = client.post(
            f"/api/v1/organizations/{second_id}/learning/import",
            json=bundle,
            headers=headers,
        )
        assert imported.status_code == 200
        outcome = imported.json()
        assert outcome["organization_settings_applied"] is True
        assert outcome["profiles_created"] >= 1

        # Learning followed the export: settings + profile now live in org 2.
        settings2 = client.get(
            f"/api/v1/organizations/{second_id}/settings", headers=headers
        ).json()
        assert settings2["default_currency"] == "INR"
        profiles2 = client.get(
            f"/api/v1/organizations/{second_id}/client-profiles", headers=headers
        ).json()
        assert any(p["name"] == "Neel Enterprise" for p in profiles2)

        # Re-import is idempotent-by-name: updates, not duplicates.
        again = client.post(
            f"/api/v1/organizations/{second_id}/learning/import",
            json=bundle, headers=headers,
        ).json()
        assert again["profiles_created"] == 0
        assert again["profiles_updated"] >= 1
