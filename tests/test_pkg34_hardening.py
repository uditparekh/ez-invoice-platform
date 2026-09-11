"""Release gates for transaction rollback, authorization and local recovery."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from siftentry_app import tally_connector_runtime as rt
from tests.test_api import (
    make_client, bootstrap, organization_id, authorization,
    _connector_profile_and_invoice, _claim, _submit_result, _invite_and_accept,
    make_text_pdf,
)


def prepared(client):
    tokens = bootstrap(client)
    org = organization_id(tokens)
    profile_id, invoice_id, headers = _connector_profile_and_invoice(client, tokens, org)
    assert client.post(f"/api/v1/invoices/{invoice_id}/validate", headers=headers).status_code == 200
    assert client.post(f"/api/v1/invoices/{invoice_id}/approve", headers=headers).status_code == 200
    return org, profile_id, invoice_id, headers


def test_claim_and_posting_insert_roll_back_together(tmp_path, monkeypatch):
    with make_client(tmp_path) as client:
        _, _, invoice_id, headers = prepared(client)
        repo = client.app.state.repository
        original = repo._insert_audit
        def fail(connection, org, invoice, event, details):
            if event == "posting.started":
                raise RuntimeError("simulated database failure")
            return original(connection, org, invoice, event, details)
        with monkeypatch.context() as patch:
            patch.setattr(repo, "_insert_audit", fail)
            with pytest.raises(RuntimeError, match="simulated database"):
                _claim(client)
        assert client.get(f"/api/v1/invoices/{invoice_id}", headers=headers).json()["status"] == "approved"
        assert len(_claim(client).json()["jobs"]) == 1


def test_invoice_and_terminal_posting_roll_back_together(tmp_path, monkeypatch):
    with make_client(tmp_path) as client:
        _, _, invoice_id, headers = prepared(client)
        job = _claim(client).json()["jobs"][0]
        repo = client.app.state.repository
        original = repo._insert_audit
        def fail(connection, org, invoice, event, details):
            if event == "posting.completed":
                raise RuntimeError("simulated commit failure")
            return original(connection, org, invoice, event, details)
        with monkeypatch.context() as patch:
            patch.setattr(repo, "_insert_audit", fail)
            with pytest.raises(RuntimeError, match="simulated commit"):
                _submit_result(client, job, True, "success")
        assert str(repo.get_posting(job["posting_id"]).status) in {"started", "PostingStatus.STARTED"}
        assert client.get(f"/api/v1/invoices/{invoice_id}", headers=headers).json()["status"] == "posting"
        assert _submit_result(client, job, True, "retry acknowledgement").json()["accepted"] == 1
        assert client.get(f"/api/v1/invoices/{invoice_id}", headers=headers).json()["status"] == "posted"


def test_concurrent_conflict_evidence_is_not_lost(tmp_path):
    with make_client(tmp_path) as client:
        prepared(client)
        job = _claim(client).json()["jobs"][0]
        _submit_result(client, job, True, "success")
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda n: _submit_result(client, job, False, f"late {n}"), range(8)))
        assert all(r.status_code == 200 for r in responses)
        posting = client.app.state.repository.get_posting(job["posting_id"])
        assert posting.success and len(posting.raw["late_result_conflicts"]) == 8


def test_accountant_cannot_replace_connector_identity(tmp_path):
    with make_client(tmp_path) as client:
        org, profile, _, owner_headers = prepared(client)
        _invite_and_accept(client, org, owner_headers, "accountant@example.com", "accountant")
        login = client.post("/api/v1/auth/login", json={"email": "accountant@example.com", "password": "member-password-is-long"})
        headers = authorization(login.json())
        url = f"/api/v1/organizations/{org}/client-profiles/{profile}"
        settings = client.get(url, headers=headers).json()["settings"]
        settings["purchase_ledger"] = "ANOTHER PURCHASE LEDGER"
        assert client.patch(url, headers=headers, json={"settings": settings}).status_code == 200
        settings["connection_settings"]["connector_token"] = "attacker-chosen"
        assert client.patch(url, headers=headers, json={"settings": settings}).status_code == 403
        assert client.get(url + "/connector-credentials", headers=headers).status_code == 403
        recommended = client.post(url + "/recommend-settings", headers=headers)
        assert recommended.status_code == 200
        assert "connector-secret" not in recommended.text
        sample = client.post(url + "/training-samples", headers=headers,
            files={"file": ("sample.pdf", make_text_pdf("Invoice 123"), "application/pdf")})
        assert sample.status_code == 200 and "connector-secret" not in sample.text


def test_live_tally_api_also_requires_approval(tmp_path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org = organization_id(tokens)
        profile, invoice, headers = _connector_profile_and_invoice(client, tokens, org)
        assert client.post(f"/api/v1/invoices/{invoice}/validate", headers=headers).status_code == 200
        response = client.post(f"/api/v1/invoices/{invoice}/post", headers=headers,
            json={"target": "tally", "client_profile_id": profile, "dry_run": False})
        assert response.status_code == 409
        assert "Approve" in response.text


@pytest.mark.parametrize("text", ["", "[7]", '[{"posting_id":"p1"}]', '{"unexpected":[]}'])
def test_malformed_outbox_is_preserved_and_blocks_claims(tmp_path, monkeypatch, text):
    config = rt.ConnectorConfig(cloud_url="https://example.invalid", token="test", config_path=str(tmp_path / "connector_config.json"))
    path = rt.default_outbox_path(config.config_path)
    path.write_text(text)
    monkeypatch.setattr(rt, "claim_cloud_jobs", lambda _: pytest.fail("must not claim"))
    result = rt.poll_once(config)
    assert not result["success"] and result["awaiting_ack"] == -1
    assert path.read_text() == text


def test_incomplete_ack_does_not_erase_outbox(tmp_path, monkeypatch):
    config = rt.ConnectorConfig(cloud_url="https://example.invalid", token="test", config_path=str(tmp_path / "connector_config.json"))
    path = rt.default_outbox_path(config.config_path)
    rt.append_outbox(path, [{"posting_id": "p1", "success": True}])
    monkeypatch.setattr(rt, "submit_cloud_results", lambda *args: {"success": True, "accepted": 0})
    assert not rt.drain_outbox(config, path)["success"]
    assert len(rt.read_outbox(path)) == 1


def test_overlapping_runtime_poll_is_blocked(tmp_path, monkeypatch):
    config = rt.ConnectorConfig(cloud_url="https://example.invalid", token="test", config_path=str(tmp_path / "connector_config.json"))
    monkeypatch.setattr(rt, "claim_cloud_jobs", lambda _: pytest.fail("must not claim"))
    with rt._poll_file_lock(rt.default_outbox_path(config.config_path)):
        result = rt.poll_once(config)
    assert not result["success"] and "another instance" in result["message"]


def test_named_configs_have_separate_outboxes(tmp_path):
    assert rt.default_outbox_path(str(tmp_path / "one.json")) != rt.default_outbox_path(str(tmp_path / "two.json"))
