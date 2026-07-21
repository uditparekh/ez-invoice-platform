"""Tests for training mode's supplier format registry and graduation."""

import os
import pathlib
import uuid

import pytest
from fastapi.testclient import TestClient

from siftentry_app.backend.domain import legacy_payload_to_invoice

from .test_domain import sample_legacy_payload


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "formats.db"
    monkeypatch.setenv("EZ_API_DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setenv("EZ_API_ALLOW_DEV_BOOTSTRAP", "true")
    monkeypatch.setenv("EZ_API_UPLOAD_DIRECTORY", str(tmp_path / "uploads"))
    from siftentry_app.backend.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def _bootstrap(client: TestClient):
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={
            "email": f"owner-{uuid.uuid4().hex[:8]}@formats.test",
            "password": "long-password-123456",
            "full_name": "Owner",
            "organization_name": "Formats Org",
            "legal_names": [],
            "default_currency": "USD",
        },
    )
    assert response.status_code in (200, 201), response.text
    payload = response.json()
    token = payload["access_token"]
    org_id = payload["user"]["memberships"][0]["organization_id"]
    return {"Authorization": f"Bearer {token}"}, org_id


def _make_invoice(client, headers, org_id, supplier_name="Crescent Bearing"):
    unique = uuid.uuid4().hex[:10]
    body = legacy_payload_to_invoice(
        sample_legacy_payload(),
        organization_id=org_id,
        source_file=f"sample-{unique}.pdf",
    ).model_dump(mode="json")
    body["invoice_number"] = f"INV-{unique}"
    body["supplier"]["name"] = supplier_name
    response = client.post(
        "/api/v1/invoices/import", headers=headers, json=body
    )
    assert response.status_code in (200, 201), response.text
    invoice = response.json()
    validate = client.post(
        f"/api/v1/invoices/{invoice['id']}/validate", headers=headers
    )
    assert validate.status_code == 200, validate.text
    assert validate.json()["status"] == "validated", validate.json()["status"]
    return invoice


def test_clean_approvals_graduate_to_trusted(client):
    headers, org_id = _bootstrap(client)
    for index in range(5):
        invoice = _make_invoice(client, headers, org_id)
        approve = client.post(
            f"/api/v1/invoices/{invoice['id']}/approve", headers=headers
        )
        assert approve.status_code == 200, approve.text

    listing = client.get(
        f"/api/v1/organizations/{org_id}/supplier-formats", headers=headers
    )
    assert listing.status_code == 200, listing.text
    payload = listing.json()
    assert payload["trusted_after_clean"] == 5
    assert len(payload["formats"]) == 1
    record = payload["formats"][0]
    assert record["status"] == "trusted"
    assert record["clean_streak"] == 5
    assert record["samples_count"] == 5


def test_correction_resets_streak_and_demotes(client):
    headers, org_id = _bootstrap(client)
    invoice = _make_invoice(client, headers, org_id)
    # PATCH records field corrections against the invoice.
    patched = client.patch(
        f"/api/v1/invoices/{invoice['id']}",
        headers=headers,
        json={"invoice_number": f"FIXED-{uuid.uuid4().hex[:6]}"},
    )
    assert patched.status_code == 200, patched.text
    # Patching returns it to extracted; walk it back to approval.
    revalidate = client.post(
        f"/api/v1/invoices/{invoice['id']}/validate", headers=headers
    )
    assert revalidate.status_code == 200, revalidate.text
    assert revalidate.json()["status"] == "validated"
    approve = client.post(
        f"/api/v1/invoices/{invoice['id']}/approve", headers=headers
    )
    assert approve.status_code == 200, approve.text

    listing = client.get(
        f"/api/v1/organizations/{org_id}/supplier-formats", headers=headers
    ).json()
    assert listing["formats"], listing
    record = listing["formats"][0]
    assert record["samples_count"] == 1
    assert record["clean_streak"] == 0
    assert record["status"] == "training"


def test_unknown_suppliers_appear_as_untrained(client):
    headers, org_id = _bootstrap(client)
    _make_invoice(client, headers, org_id, supplier_name="Never Trained Co")
    listing = client.get(
        f"/api/v1/organizations/{org_id}/supplier-formats", headers=headers
    ).json()
    assert listing["formats"] == []
    assert listing["untrained"]
    assert listing["untrained"][0]["supplier_name"] == "Never Trained Co"
    assert listing["untrained"][0]["invoice_count"] == 1
