import pytest

from siftentry_app.backend.models import ClientProfilePatch
from tests.test_api import (approve_with_preview, make_client, bootstrap, organization_id, authorization,
                            _tally_profile_body, _connector_profile_and_invoice)


@pytest.mark.parametrize("token", ["secret—token", "secret\ntoken", "has space", "x" * 513])
def test_invalid_new_token_is_rejected_without_echo(tmp_path, token):
    with make_client(tmp_path) as client:
        owner = bootstrap(client)
        body = _tally_profile_body("Tally", True)
        body["settings"]["connection_settings"]["connector_token"] = token
        response = client.post(f"/api/v1/organizations/{organization_id(owner)}/client-profiles",
                               json=body, headers=authorization(owner))
        assert response.status_code == 422
        assert token not in response.text


def test_legacy_non_ascii_stored_token_returns_401_not_500(tmp_path):
    with make_client(tmp_path) as client:
        owner = bootstrap(client)
        org = organization_id(owner)
        profile, _, _ = _connector_profile_and_invoice(client, owner, org)
        repository = client.app.state.repository
        settings = repository.get_client_profile(profile).settings.model_copy(deep=True)
        settings.connection_settings["connector_token"] = "legacy—secret"
        repository.update_client_profile(profile, ClientProfilePatch(settings=settings))
        for path in ["diagnostics", "heartbeat", "jobs/claim", "jobs/results"]:
            response = client.post("/api/v1/connectors/tally/" + path,
                json={"workspace_id": "neel-prod", "results": []},
                headers={"Authorization": "Bearer connector-secret"})
            assert response.status_code == 401
            assert "legacy" not in response.text


def test_non_ascii_supplied_token_returns_401(tmp_path):
    with make_client(tmp_path) as client:
        # ASGI receives latin-1 headers; malformed byte values must not crash hmac.
        response = client.post("/api/v1/connectors/tally/diagnostics",
            json={"workspace_id": "neel-prod"}, headers={b"authorization": b"Bearer nonascii\xe9"})
        assert response.status_code == 401


def test_empty_workspace_diagnostics_and_poll_are_successful(tmp_path):
    with make_client(tmp_path) as client:
        owner = bootstrap(client)
        org = organization_id(owner)
        body = _tally_profile_body("Tally", True)
        created = client.post(f"/api/v1/organizations/{org}/client-profiles", json=body, headers=authorization(owner))
        assert created.status_code == 201
        headers = {"Authorization": "Bearer connector-secret"}
        result = client.post("/api/v1/connectors/tally/diagnostics", json={"workspace_id": "neel-prod"}, headers=headers)
        assert result.status_code == 200 and result.json()["success"]
        assert "connector-secret" not in result.text
        assert client.app.state.repository.get_connector_heartbeat(created.json()["id"]) is None
        result = client.post("/api/v1/connectors/tally/jobs/claim", json={"workspace_id": "neel-prod"}, headers=headers)
        assert result.status_code == 200 and result.json()["jobs"] == []


def test_diagnostics_does_not_claim_approved_invoice(tmp_path):
    with make_client(tmp_path) as client:
        owner = bootstrap(client)
        profile, invoice, headers = _connector_profile_and_invoice(client, owner, organization_id(owner))
        assert client.post(f"/api/v1/invoices/{invoice}/validate", headers=headers).status_code == 200
        assert approve_with_preview(client, invoice, headers).status_code == 200
        result = client.post("/api/v1/connectors/tally/diagnostics", json={"workspace_id": "neel-prod"},
                             headers={"Authorization": "Bearer connector-secret"})
        assert result.status_code == 200
        repo = client.app.state.repository
        assert repo.get_invoice(invoice).status == "approved"
        assert repo.list_postings_for_invoice(invoice) == []
        assert repo.get_connector_heartbeat(profile) is None
