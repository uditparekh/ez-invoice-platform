from pathlib import Path

from fastapi.testclient import TestClient

from ez_invoice_app.backend.domain import legacy_payload_to_invoice
from ez_invoice_app.backend.main import create_app
from ez_invoice_app.backend.models import InvoiceStatus
from ez_invoice_app.backend.settings import ApiSettings

from .test_domain import sample_legacy_payload


def make_client(tmp_path: Path) -> TestClient:
    app = create_app(
        ApiSettings(
            database_path=tmp_path / "api.db",
            upload_directory=tmp_path / "uploads",
            max_upload_bytes=2 * 1024 * 1024,
            cors_origins=("http://localhost:3000",),
            jwt_secret="test-secret-that-is-not-used-in-production",
            access_token_minutes=5,
            refresh_token_days=2,
            allow_dev_bootstrap=True,
            environment="test",
        )
    )
    return TestClient(app)


def bootstrap(
    client: TestClient,
    email: str = "owner@example.com",
    password: str = "correct-horse-battery-staple",
    organization_name: str = "Example Client",
) -> dict:
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={
            "email": email,
            "password": password,
            "full_name": "Owner",
            "organization_name": organization_name,
            "legal_names": [organization_name],
            "default_currency": "INR",
        },
    )
    assert response.status_code == 201
    return response.json()


def authorization(tokens: dict) -> dict:
    return {"Authorization": "Bearer " + tokens["access_token"]}


def organization_id(tokens: dict, name: str = "Example Client") -> str:
    membership = next(
        item for item in tokens["user"]["memberships"] if item["organization_name"] == name
    )
    return membership["organization_id"]


def import_sample_invoice(
    client: TestClient,
    tokens: dict,
    target_organization_id: str,
    source_file: str = "sample.pdf",
) -> dict:
    body = legacy_payload_to_invoice(
        sample_legacy_payload(),
        organization_id=target_organization_id,
        source_file=source_file,
    ).model_dump(mode="json")
    response = client.post(
        "/api/v1/invoices/import",
        json=body,
        headers=authorization(tokens),
    )
    assert response.status_code == 201
    return response.json()


def test_authentication_and_invoice_workflow(tmp_path: Path):
    with make_client(tmp_path) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        assert client.get("/api/v1/organizations").status_code == 401
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        headers = authorization(tokens)

        me = client.get("/api/v1/auth/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["email"] == "owner@example.com"
        assert me.json()["memberships"][0]["role"] == "owner"

        invoice = import_sample_invoice(client, tokens, org_id)
        invoice_id = invoice["id"]

        validated = client.post(
            f"/api/v1/invoices/{invoice_id}/validate",
            headers=headers,
        )
        assert validated.status_code == 200
        assert validated.json()["valid"] is True
        assert validated.json()["status"] == InvoiceStatus.VALIDATED.value

        approved = client.post(
            f"/api/v1/invoices/{invoice_id}/approve",
            headers=headers,
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == InvoiceStatus.APPROVED.value

        dry_run = client.post(
            f"/api/v1/invoices/{invoice_id}/post",
            json={"target": "quickbooks", "dry_run": True},
            headers=headers,
        )
        assert dry_run.status_code == 200
        assert dry_run.json()["success"] is True
        assert dry_run.json()["dry_run"] is True

        posting_result = client.post(
            f"/api/v1/invoices/{invoice_id}/posting-results",
            json={
                "target": "quickbooks",
                "success": True,
                "message": "Bill created.",
                "external_id": "bill-100",
                "raw": {"bill_id": "bill-100"},
            },
            headers=headers,
        )
        assert posting_result.status_code == 201
        assert posting_result.json()["external_id"] == "bill-100"

        posted_invoice = client.get(
            f"/api/v1/invoices/{invoice_id}",
            headers=headers,
        )
        assert posted_invoice.json()["status"] == InvoiceStatus.POSTED.value

        refreshed = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert refreshed.status_code == 200
        assert refreshed.json()["refresh_token"] != tokens["refresh_token"]
        reused = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert reused.status_code == 401

        refreshed_headers = authorization(refreshed.json())
        cleared = client.delete(
            f"/api/v1/organizations/{org_id}/invoices",
            headers=refreshed_headers,
        )
        assert cleared.status_code == 200
        assert cleared.json()["deleted"] == 1
        assert client.get(
            "/api/v1/invoices",
            params={"organization_id": org_id},
            headers=refreshed_headers,
        ).json() == []


def test_tenant_isolation_and_role_permissions(tmp_path: Path):
    with make_client(tmp_path) as client:
        owner_tokens = bootstrap(client)
        owner_headers = authorization(owner_tokens)
        organization_a = organization_id(owner_tokens)

        organization_b_response = client.post(
            "/api/v1/organizations",
            json={
                "name": "Second Client",
                "legal_names": ["Second Client Private Limited"],
                "default_currency": "INR",
            },
            headers=owner_headers,
        )
        assert organization_b_response.status_code == 201
        organization_b = organization_b_response.json()["id"]

        invoice_a = import_sample_invoice(
            client,
            owner_tokens,
            organization_a,
            source_file="client-a.pdf",
        )
        invoice_b = import_sample_invoice(
            client,
            owner_tokens,
            organization_b,
            source_file="client-b.pdf",
        )

        invitation = client.post(
            f"/api/v1/organizations/{organization_b}/invitations",
            json={"email": "viewer@example.com", "role": "viewer"},
            headers=owner_headers,
        )
        assert invitation.status_code == 201
        invitation_token = invitation.json()["invitation_token"]
        assert invitation_token

        viewer_tokens_response = client.post(
            "/api/v1/auth/invitations/accept",
            json={
                "token": invitation_token,
                "password": "viewer-password-is-long",
                "full_name": "Viewer",
            },
        )
        assert viewer_tokens_response.status_code == 200
        viewer_tokens = viewer_tokens_response.json()
        viewer_headers = authorization(viewer_tokens)

        allowed_list = client.get(
            "/api/v1/invoices",
            params={"organization_id": organization_b},
            headers=viewer_headers,
        )
        assert allowed_list.status_code == 200
        assert [item["id"] for item in allowed_list.json()] == [invoice_b["id"]]

        denied_list = client.get(
            "/api/v1/invoices",
            params={"organization_id": organization_a},
            headers=viewer_headers,
        )
        assert denied_list.status_code == 404

        denied_invoice = client.get(
            f"/api/v1/invoices/{invoice_a['id']}",
            headers=viewer_headers,
        )
        assert denied_invoice.status_code == 404

        viewer_import = legacy_payload_to_invoice(
            sample_legacy_payload(),
            organization_id=organization_b,
            source_file="viewer-upload.pdf",
        ).model_dump(mode="json")
        denied_upload = client.post(
            "/api/v1/invoices/import",
            json=viewer_import,
            headers=viewer_headers,
        )
        assert denied_upload.status_code == 403

        denied_validate = client.post(
            f"/api/v1/invoices/{invoice_b['id']}/validate",
            headers=viewer_headers,
        )
        assert denied_validate.status_code == 403

        denied_clear = client.delete(
            f"/api/v1/organizations/{organization_b}/invoices",
            headers=viewer_headers,
        )
        assert denied_clear.status_code == 403

        approver_invitation = client.post(
            f"/api/v1/organizations/{organization_b}/invitations",
            json={"email": "approver@example.com", "role": "approver"},
            headers=owner_headers,
        ).json()
        approver_tokens = client.post(
            "/api/v1/auth/invitations/accept",
            json={
                "token": approver_invitation["invitation_token"],
                "password": "approver-password-is-long",
                "full_name": "Approver",
            },
        ).json()
        approver_headers = authorization(approver_tokens)
        assert client.post(
            f"/api/v1/invoices/{invoice_b['id']}/validate",
            headers=approver_headers,
        ).status_code == 200
        assert client.post(
            f"/api/v1/invoices/{invoice_b['id']}/approve",
            headers=approver_headers,
        ).status_code == 200
        assert client.post(
            f"/api/v1/invoices/{invoice_b['id']}/post",
            json={"target": "quickbooks", "dry_run": True},
            headers=approver_headers,
        ).status_code == 403

        accountant_invitation = client.post(
            f"/api/v1/organizations/{organization_b}/invitations",
            json={"email": "accountant@example.com", "role": "accountant"},
            headers=owner_headers,
        ).json()
        accountant_tokens = client.post(
            "/api/v1/auth/invitations/accept",
            json={
                "token": accountant_invitation["invitation_token"],
                "password": "accountant-password-is-long",
                "full_name": "Accountant",
            },
        ).json()
        accountant_headers = authorization(accountant_tokens)
        assert client.post(
            f"/api/v1/invoices/{invoice_b['id']}/post",
            json={"target": "quickbooks", "dry_run": True},
            headers=accountant_headers,
        ).status_code == 200
        assert client.post(
            f"/api/v1/organizations/{organization_b}/invitations",
            json={"email": "blocked@example.com", "role": "viewer"},
            headers=accountant_headers,
        ).status_code == 403


def test_upload_rejects_non_pdf_after_authentication(tmp_path: Path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        response = client.post(
            "/api/v1/invoices/upload",
            params={"organization_id": org_id},
            files={"file": ("invoice.txt", b"not a pdf", "text/plain")},
            headers=authorization(tokens),
        )
        assert response.status_code == 415


def test_clear_queue_removes_stored_pdf(tmp_path: Path):
    import fitz

    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        document = fitz.open()
        page = document.new_page()
        page.insert_text(
            (72, 72),
            "INVOICE INV-200\nSupplier Example\nInvoice Date 19-JUN-2026\nTotal INR 118.00",
        )
        pdf_bytes = document.tobytes()
        document.close()

        uploaded = client.post(
            "/api/v1/invoices/upload",
            params={"organization_id": org_id},
            files={"file": ("stored.pdf", pdf_bytes, "application/pdf")},
            headers=authorization(tokens),
        )
        assert uploaded.status_code == 201
        stored_path = Path(uploaded.json()["source_path"])
        assert stored_path.exists()

        cleared = client.delete(
            f"/api/v1/organizations/{org_id}/invoices",
            headers=authorization(tokens),
        )
        assert cleared.status_code == 200
        assert not stored_path.exists()
