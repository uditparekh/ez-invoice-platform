import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest

from siftentry_app.backend.extraction_benchmarks import (
    ExpectedExtraction,
    compare,
    extraction_scope,
    field_values,
    quality_reasons,
)
from siftentry_app.backend.extraction_common import parse_json_block
from siftentry_app.backend.parser_service import parse_pdf_invoice
from siftentry_app.backend.worker import run_once
from .test_api import (
    make_client,
    bootstrap,
    authorization,
    organization_id,
    make_text_pdf,
)


def pdf(number="INV-101", currency="USD", label="Invoice No"):
    return make_text_pdf(
        f"ACME Supplies\n{label}: {number}\nInvoice Date: 2026-09-22\nDue Date: 2026-09-22\nBill To: Pilot Client\nCurrency: {currency}\nDescription Quantity Unit Price Amount\nWidgets 2 50.00 100.00\nSubtotal: 100.00\nTax: 0.00\nTotal: {currency} 100.00"
    )


def expected(content):
    # Test fixture only: real users must independently confirm PDF values.
    result = field_values(
        parse_pdf_invoice("fixture.pdf", content, "test", ["Pilot Client"])
    )
    for field in ("invoice_date", "due_date"):
        result[field] = datetime.strptime(result[field], "%d-%b-%Y").date().isoformat()
    return result


@pytest.fixture
def setup(tmp_path):
    with make_client(tmp_path) as client:
        token = bootstrap(client)
        org = organization_id(token)
        headers = authorization(token)
        response = client.post(
            f"/api/v1/organizations/{org}/client-profiles",
            headers=headers,
            json={
                "name": "Evidence profile",
                "accounting_system": "excel",
                "is_default": True,
            },
        )
        assert response.status_code == 201, response.text
        profile = response.json()["id"]
        url = (
            f"/api/v1/organizations/{org}/client-profiles/{profile}/extraction-evidence"
        )
        yield client, headers, org, profile, url


def add(setup, number="INV-101", split="held_out", override=None):
    client, headers, _, _, url = setup
    content = pdf(number)
    body = {
        "expected": expected(content),
        "split": split,
        "confirmed": True,
        "retain_for_checks": True,
        "review_seconds": 90,
    }
    if override:
        body.update(override)
    return client.post(
        url + "/samples",
        headers=headers,
        files={"file": (number + ".pdf", content, "application/pdf")},
        data={"confirmation": json.dumps(body)},
    )


def test_replay_reports_real_field_failures_and_never_creates_invoices(setup):
    client, headers, org, profile, url = setup
    content = pdf()
    values = expected(content)
    values["total"] = 999
    assert add(setup, override={"expected": values}).status_code == 201
    response = client.post(url + "/runs", headers=headers, json={})
    assert response.status_code == 202, response.text
    assert client.post(url + "/runs", headers=headers, json={}).status_code == 409
    assert run_once(client.app)
    view = client.get(url, headers=headers).json()
    assert view["job"]["status"] == "done", view
    result = view["job"]["result"]
    assert result["summary"]["held_out"]["baseline"]["passed_documents"] == 0
    checks = result["samples"][0]["baseline"]["checks"]
    assert next(c for c in checks if c["field"] == "total")["match"] is False
    assert result["samples"][0]["review_seconds"] == 90
    assert client.app.state.repository.list_invoices(org) == []
    assert "storage_json" not in view["samples"][0]


def test_lessons_are_scoped_anchors_not_values_or_held_out_answers(setup):
    client, headers, _, profile_id, url = setup
    train = add(setup, split="learning").json()["id"]
    held = add(setup, "INV-102").json()["id"]
    lesson = {
        "sample_id": held,
        "field": "invoice_number",
        "anchor": "Invoice No",
        "relation": "after_label",
        "confirmed": True,
    }
    assert (
        client.post(url + "/lessons", headers=headers, json=lesson).status_code == 409
    )
    lesson["sample_id"] = train
    for bad in ("INV-101", "ACME Supplies", "Not printed anywhere"):
        assert (
            client.post(
                url + "/lessons", headers=headers, json={**lesson, "anchor": bad}
            ).status_code
            == 422
        )
    assert (
        client.post(url + "/lessons", headers=headers, json=lesson).status_code == 201
    )
    repo = client.app.state.repository
    sample = next(s for s in repo.benchmark_samples(profile_id) if s["id"] == train)
    scope = sample["scope"]
    assert len(repo.benchmark_lessons(profile_id, scope)) == 1
    for key, value in (
        ("supplier_key", "other"),
        ("layout", "changed"),
        ("currency", "INR"),
        ("profile_id", "other"),
        ("document_type", "credit_note"),
    ):
        assert repo.benchmark_lessons(profile_id, {**scope, key: value}) == []
    assert repo.benchmark_lessons(profile_id, scope, train) == []
    # Deleting does not allow relabeling this learning document as held-out.
    assert client.delete(url + "/sample/" + train, headers=headers).status_code == 200
    assert add(setup).status_code == 409
    assert repo.benchmark_lessons(profile_id) == []


def test_five_independent_held_out_matches_required_and_changes_invalidate(setup):
    client, headers, org, profile_id, url = setup
    for i in range(5):
        response = add(setup, f"INV-{i}")
        assert response.status_code == 201, response.text
    assert client.post(url + "/runs", headers=headers, json={}).status_code == 202
    assert run_once(client.app)
    repo = client.app.state.repository
    profile = repo.get_client_profile(profile_id)
    scope = repo.benchmark_samples(profile_id)[0]["scope"]
    assert (
        repo.extraction_guidance(profile, scope, ["arithmetic_mismatch"])["allow_skip"]
        is False
    )
    guidance = repo.extraction_guidance(profile, scope, [])
    assert guidance["allow_skip"] is True, client.get(url, headers=headers).json()[
        "job"
    ]
    assert (
        repo.extraction_guidance(profile, {**scope, "currency": "EUR"}, [])[
            "allow_skip"
        ]
        is False
    )
    # A new sample invalidates the report, rather than silently extending qualification.
    assert add(setup, "INV-NEW").status_code == 201
    assert repo.extraction_guidance(profile, scope, [])["allow_skip"] is False
    assert client.get(url, headers=headers).json()["job"]["current"] is False


def test_concurrent_run_requests_are_serialized(setup):
    client, headers, _, profile, _ = setup
    assert add(setup).status_code == 201
    repo = client.app.state.repository

    def queue(_):
        try:
            return repo.queue_benchmark(
                repo.get_client_profile(profile),
                client.app.state.ai_extractor_config,
                False,
                "test",
            ).id
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(queue, range(2)))
    assert len([r for r in results if r]) == 1


def test_missing_or_changed_pdf_is_failure_not_a_pass(setup):
    client, headers, _, profile_id, url = setup
    assert add(setup).status_code == 201
    assert client.post(url + "/runs", headers=headers, json={}).status_code == 202
    sample = client.app.state.repository.benchmark_samples(profile_id)[0]
    from siftentry_app.backend.storage import StoredDocument

    client.app.state.storage.delete(
        StoredDocument(**json.loads(sample["storage_json"]))
    )
    assert run_once(client.app)
    result = client.get(url, headers=headers).json()["job"]["result"]
    assert result["summary"]["held_out"]["errors"] == 1
    assert result["summary"]["held_out"]["baseline"]["accuracy"] is None


def test_failed_storage_deletion_remains_durable_and_retryable(setup, monkeypatch):
    client, headers, _, profile_id, url = setup
    sample_id = add(setup).json()["id"]
    storage = client.app.state.storage
    real_delete = storage.delete
    monkeypatch.setattr(storage, "delete", lambda target: None)
    assert (
        client.delete(url + "/sample/" + sample_id, headers=headers).status_code == 200
    )
    view = client.get(url, headers=headers).json()
    assert view["samples"] == []
    assert view["pending_pdf_deletions"] == 1
    monkeypatch.setattr(storage, "delete", real_delete)
    from siftentry_app.backend.benchmark_service import cleanup_benchmark_pdfs

    cleanup_benchmark_pdfs(client.app)
    assert client.get(url, headers=headers).json()["pending_pdf_deletions"] == 0


def test_profile_deletion_queues_sample_removal_and_cancels_checks(setup):
    client, headers, org, profile_id, url = setup
    assert add(setup).status_code == 201
    job = client.post(url + "/runs", headers=headers, json={}).json()
    response = client.delete(
        f"/api/v1/organizations/{org}/client-profiles/{profile_id}", headers=headers
    )
    assert response.status_code in (200, 204), response.text
    repo = client.app.state.repository
    assert repo.get_job(job["id"]).status == "failed"
    assert len(repo.pending_benchmark_deletions()) == 1
    from siftentry_app.backend.benchmark_service import cleanup_benchmark_pdfs

    cleanup_benchmark_pdfs(client.app)
    assert repo.pending_benchmark_deletions() == []


def test_consent_and_cross_tenant_isolation(setup):
    client, headers, _, _, url = setup
    assert add(setup, override={"confirmed": False}).status_code == 422
    assert add(setup, override={"retain_for_checks": False}).status_code == 422
    from siftentry_app.backend.security import hash_password

    client.app.state.repository.create_user(
        "other@example.com", hash_password("other-password-123"), "Other"
    )
    other = client.post(
        "/api/v1/auth/login",
        json={"email": "other@example.com", "password": "other-password-123"},
    ).json()
    assert client.get(url, headers=authorization(other)).status_code in (403, 404)
    assert client.post(
        url + "/runs", headers=authorization(other), json={}
    ).status_code in (403, 404)
    assert client.get(url).status_code == 401


def test_viewer_can_read_but_cannot_change_evidence(setup):
    client, headers, org, _, url = setup
    from siftentry_app.backend.security import hash_password
    from siftentry_app.backend.models import OrganizationRole

    repo = client.app.state.repository
    viewer = repo.create_user(
        "viewer@example.com", hash_password("viewer-password-123"), "Viewer"
    )
    repo.create_membership(viewer.id, org, OrganizationRole.VIEWER)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": viewer.email, "password": "viewer-password-123"},
    ).json()
    auth = authorization(token)
    assert client.get(url, headers=auth).status_code == 200
    for endpoint in ("runs", "cancel"):
        assert (
            client.post(url + "/" + endpoint, headers=auth, json={}).status_code == 403
        )


def test_cancelled_worker_cannot_overwrite_terminal_state(setup):
    client, headers, _, profile, url = setup
    assert add(setup).status_code == 201
    job = client.post(url + "/runs", headers=headers, json={}).json()
    repo = client.app.state.repository
    assert repo.claim_next_job().id == job["id"]
    assert client.post(url + "/cancel", headers=headers).status_code == 200
    repo.finish_job(job["id"], result={"pretend": "success"})
    assert repo.get_job(job["id"]).status == "failed"
    assert repo.get_job(job["id"]).result == {}
    assert client.post(url + "/runs", headers=headers, json={}).status_code == 202


def test_ai_replay_receives_scoped_hints_but_not_expected_answers(setup, monkeypatch):
    client, headers, _, profile_id, url = setup
    train = add(setup, "INV-101", "learning").json()["id"]
    assert add(setup, "INV-102").status_code == 201
    assert (
        client.post(
            url + "/lessons",
            headers=headers,
            json={
                "sample_id": train,
                "field": "invoice_number",
                "anchor": "Invoice No",
                "relation": "after_label",
                "confirmed": True,
            },
        ).status_code
        == 201
    )
    from siftentry_app.backend.ai_parser import AiExtractorConfig

    client.app.state.ai_extractor_config = AiExtractorConfig(
        provider="openai_compatible",
        api_key="test-key",
        base_url="https://fixture.invalid/v1",
        model="fixture",
    )
    seen = []

    def fake_extract(**kwargs):
        context = kwargs["context"]
        seen.append(context)
        assert "INV-101" not in json.dumps(context) and "INV-102" not in json.dumps(
            context
        )
        assert (
            "purchase_ledger" not in context
            and "posting_expectations" not in context["training"]
        )
        return {
            "suggestions": {
                "invoice_number": {
                    "value": "WRONG",
                    "confidence": 1,
                    "reason": "fixture",
                }
            },
            "model": "fixture",
            "latency_ms": 1,
            "error": "",
        }

    monkeypatch.setattr(
        "siftentry_app.backend.openai_extractor.extract_with_openai_compatible",
        fake_extract,
    )
    assert (
        client.post(
            url + "/runs", headers=headers, json={"include_ai": True}
        ).status_code
        == 202
    )
    assert run_once(client.app)
    result = client.get(url, headers=headers).json()["job"]["result"]
    assert len(seen) == 2
    assert seen[0]["extraction_lessons"] == []
    assert seen[1]["extraction_lessons"][0]["anchor"] == "Invoice No"
    assert result["samples"][1]["ai"]["passed"] is False
    assert result["samples"][1]["baseline"]["passed"] is True


def test_correction_opt_out_still_invalidates_routing_evidence(setup):
    client, headers, org, profile_id, url = setup
    response = client.post(
        f"/api/v1/invoices/upload?organization_id={org}&client_profile_id={profile_id}",
        headers=headers,
        files={"file": ("test.pdf", pdf(), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    repo = client.app.state.repository
    before = repo.extraction_revision_number(profile_id)
    invoice = response.json()
    patch = client.patch(
        f"/api/v1/invoices/{invoice['id']}",
        headers=headers,
        json={"invoice_number": "CORRECTED", "learn_vendor_memory": False},
    )
    assert patch.status_code == 200, patch.text
    assert repo.extraction_revision_number(profile_id) == before + 1
    assert repo.list_correction_learning_signals(org) == []


def test_real_upload_route_skips_ai_only_with_current_matching_evidence(
    setup, monkeypatch
):
    client, headers, org, profile_id, url = setup
    for index in range(5):
        assert add(setup, f"INV-{index}").status_code == 201
    assert client.post(url + "/runs", headers=headers, json={}).status_code == 202
    assert run_once(client.app)
    from siftentry_app.backend.ai_parser import AiExtractorConfig

    client.app.state.ai_extractor_config = AiExtractorConfig(
        provider="openai_compatible", api_key="fixture", model="fixture"
    )
    calls = []

    def fake(*args, **kwargs):
        calls.append(kwargs)
        return {
            "provider": "fixture",
            "configured": True,
            "policy": "review_only",
            "suggestions": {},
            "error": "",
        }

    monkeypatch.setattr(
        "siftentry_app.backend.ai_parser.request_external_ai_suggestions", fake
    )

    def upload(content):
        response = client.post(
            f"/api/v1/invoices/upload?organization_id={org}",
            headers=headers,
            files={"file": ("new.pdf", content, "application/pdf")},
        )
        assert response.status_code == 201, response.text
        return response.json()

    matched = upload(pdf("INV-NEW"))
    assert matched["raw_payload"]["_extraction_routing"]["evidence_qualified"] is True
    assert calls == []
    upload(pdf("INV-EUR", currency="EUR"))
    upload(pdf("INV-LAYOUT", label="Document No"))
    assert len(calls) == 2
    assert (
        client.patch(
            f"/api/v1/invoices/{matched['id']}",
            headers=headers,
            json={"total": 105, "learn_vendor_memory": False},
        ).status_code
        == 200
    )
    upload(pdf("INV-AFTER-CORRECTION"))
    assert len(calls) == 3


def test_expired_benchmark_cannot_qualify_routing(setup):
    client, headers, _, profile_id, url = setup
    for index in range(5):
        assert add(setup, f"INV-{index}").status_code == 201
    job = client.post(url + "/runs", headers=headers, json={}).json()
    assert run_once(client.app)
    repo = client.app.state.repository
    scope = repo.benchmark_samples(profile_id)[0]["scope"]
    profile = repo.get_client_profile(profile_id)
    assert repo.extraction_guidance(profile, scope, [])["allow_skip"]
    with repo._connect() as connection:
        connection.execute(
            "UPDATE jobs SET updated_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00+00:00", job["id"]),
        )
    assert not repo.extraction_guidance(profile, scope, [])["allow_skip"]


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"fields": []},
        {"fields": {"ledger": {"value": "Bank"}}},
        {"fields": {"total": {"value": "NaN"}}},
        {"fields": {"total": {"value": {"tool": "post"}}}},
        {"fields": {"total": {"value": "2", "confidence": 7}}},
        {"lines": [{"description": "x", "amount": "Infinity"}]},
    ],
)
def test_invalid_model_output_fails_closed(payload):
    value, error = parse_json_block(json.dumps(payload))
    assert value == {} and error


def test_numeric_and_date_comparison_and_routing_risks():
    values = expected(pdf())
    assert compare(
        values, {**values, "total": "100.000", "invoice_date": "22-SEP-2026"}
    )["passed"]
    assert not compare(values, {**values, "total": "100.01"})["passed"]
    scope = extraction_scope(
        "p", values, "Invoice No Invoice Date Subtotal Total Quantity", 1
    )
    assert "arithmetic_mismatch" in quality_reasons(
        {**values, "total": 20}, "text " * 30, scope
    )
    assert "weak_text_layer" in quality_reasons(values, "bad scan", scope)
    assert "non_invoice_document" in quality_reasons(
        values, "text " * 30, {**scope, "document_type": "credit_note"}
    )
    with pytest.raises(ValueError):
        ExpectedExtraction.model_validate({**values, "total": float("inf")})
