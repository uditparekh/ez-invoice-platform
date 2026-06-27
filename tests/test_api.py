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
            database_url=f"sqlite:///{tmp_path / 'api.db'}",
            database_path=tmp_path / "api.db",
            upload_directory=tmp_path / "uploads",
            max_upload_bytes=2 * 1024 * 1024,
            cors_origins=("http://localhost:3000",),
            app_base_url="http://testserver",
            jwt_secret="test-secret-that-is-not-used-in-production",
            access_token_minutes=5,
            refresh_token_days=2,
            allow_dev_bootstrap=True,
            environment="test",
            email_provider="memory",
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

        members = client.get(
            f"/api/v1/organizations/{org_id}/members",
            headers=headers,
        )
        assert members.status_code == 200
        assert members.json()[0]["email"] == "owner@example.com"
        assert members.json()[0]["role"] == "owner"

        bad_password_change = client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": "wrong-password",
                "new_password": "new-password-is-long",
            },
            headers=headers,
        )
        assert bad_password_change.status_code == 401
        password_change = client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": "correct-horse-battery-staple",
                "new_password": "new-password-is-long",
            },
            headers=headers,
        )
        assert password_change.status_code == 204
        old_login = client.post(
            "/api/v1/auth/login",
            json={
                "email": "owner@example.com",
                "password": "correct-horse-battery-staple",
            },
        )
        assert old_login.status_code == 401
        new_login = client.post(
            "/api/v1/auth/login",
            json={
                "email": "owner@example.com",
                "password": "new-password-is-long",
            },
        )
        assert new_login.status_code == 200

        invoice = import_sample_invoice(client, tokens, org_id)
        invoice_id = invoice["id"]

        corrected = client.patch(
            f"/api/v1/invoices/{invoice_id}",
            json={
                "invoice_number": "INV-CORRECTED",
                "currency": "usd",
                "total": invoice["total"],
                "supplier": {
                    **invoice["supplier"],
                    "name": "Corrected Supplier LLC",
                },
            },
            headers=headers,
        )
        assert corrected.status_code == 200
        assert corrected.json()["invoice_number"] == "INV-CORRECTED"
        assert corrected.json()["currency"] == "USD"
        assert corrected.json()["supplier"]["name"] == "Corrected Supplier LLC"
        assert corrected.json()["status"] == InvoiceStatus.EXTRACTED.value

        learning = client.get(
            f"/api/v1/organizations/{org_id}/corrections/learning",
            headers=headers,
        )
        assert learning.status_code == 200
        learned_fields = {item["field_path"] for item in learning.json()}
        assert {"invoice_number", "currency", "supplier"} <= learned_fields

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


def test_password_reset_flow(tmp_path: Path):
    with make_client(tmp_path) as client:
        bootstrap(client)

        unknown = client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": "missing@example.com"},
        )
        assert unknown.status_code == 200
        assert unknown.json()["reset_token"] is None

        requested = client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": "owner@example.com"},
        )
        assert requested.status_code == 200
        reset_payload = requested.json()
        assert reset_payload["reset_token"]
        assert reset_payload["expires_at"]
        assert len(client.app.state.email.outbox) == 1
        assert client.app.state.email.outbox[0].to_email == "owner@example.com"
        assert "/reset-password?token=" in client.app.state.email.outbox[0].text_body

        invalid = client.post(
            "/api/v1/auth/password-reset/confirm",
            json={
                "token": "not-a-real-reset-token-but-long-enough",
                "new_password": "reset-password-is-long",
            },
        )
        assert invalid.status_code == 400

        confirmed = client.post(
            "/api/v1/auth/password-reset/confirm",
            json={
                "token": reset_payload["reset_token"],
                "new_password": "reset-password-is-long",
            },
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["user"]["email"] == "owner@example.com"

        reused = client.post(
            "/api/v1/auth/password-reset/confirm",
            json={
                "token": reset_payload["reset_token"],
                "new_password": "another-reset-password",
            },
        )
        assert reused.status_code == 400

        old_login = client.post(
            "/api/v1/auth/login",
            json={
                "email": "owner@example.com",
                "password": "correct-horse-battery-staple",
            },
        )
        assert old_login.status_code == 401
        new_login = client.post(
            "/api/v1/auth/login",
            json={
                "email": "owner@example.com",
                "password": "reset-password-is-long",
            },
        )
        assert new_login.status_code == 200


def test_profile_owned_posting_and_retry_history(tmp_path: Path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        headers = authorization(tokens)
        invoice = import_sample_invoice(client, tokens, org_id)
        invoice_id = invoice["id"]

        validated = client.post(
            f"/api/v1/invoices/{invoice_id}/validate",
            headers=headers,
        )
        assert validated.status_code == 200

        profile_response = client.post(
            f"/api/v1/organizations/{org_id}/client-profiles",
            json={
                "name": "QuickBooks AP",
                "accounting_system": "quickbooks",
                "description": "Profile-owned QuickBooks posting setup.",
                "is_default": True,
                "settings": {
                    "company_name": "Example Client",
                    "default_currency": "USD",
                    "posting_mode": "supplier_bill",
                    "purchase_ledger": "Purchases A/C",
                    "connection_settings": {
                        "environment": "sandbox",
                        "client_id": "sandbox-client",
                        "client_secret": "sandbox-secret",
                    },
                    "item_mappings": [
                        {
                            "source_description_contains": "material",
                            "source_hsn_sac": "1234",
                            "target_item_name": "Mapped Material",
                            "target_uom": "EA",
                            "purchase_ledger": "Purchases A/C",
                            "metadata": {
                                "category": "materials",
                                "gl_code": "5000",
                            },
                        }
                    ],
                },
            },
            headers=headers,
        )
        assert profile_response.status_code == 201
        profile = profile_response.json()

        target_required = client.post(
            f"/api/v1/invoices/{invoice_id}/post",
            json={"dry_run": True},
            headers=headers,
        )
        assert target_required.status_code == 400

        mismatch = client.post(
            f"/api/v1/invoices/{invoice_id}/post",
            json={
                "target": "tally",
                "client_profile_id": profile["id"],
                "dry_run": True,
            },
            headers=headers,
        )
        assert mismatch.status_code == 409

        first_post = client.post(
            f"/api/v1/invoices/{invoice_id}/post",
            json={"client_profile_id": profile["id"], "dry_run": True},
            headers=headers,
        )
        assert first_post.status_code == 200
        first_payload = first_post.json()
        assert first_payload["success"] is True
        assert first_payload["target"] == "quickbooks"
        assert first_payload["client_profile_id"] == profile["id"]
        assert (
            first_payload["request_payload"]["posting_plan"]["profile"]["name"]
            == "QuickBooks AP"
        )
        assert (
            first_payload["request_payload"]["posting_plan"]["profile"]["settings"]
            ["connection_settings"]["client_secret"]
            == "[redacted]"
        )

        retry = client.post(
            f"/api/v1/postings/{first_payload['id']}/retry",
            json={},
            headers=headers,
        )
        assert retry.status_code == 200
        retry_payload = retry.json()
        assert retry_payload["id"] != first_payload["id"]
        assert retry_payload["target"] == "quickbooks"
        assert retry_payload["client_profile_id"] == profile["id"]
        assert retry_payload["request_payload"]["retry_of"] == first_payload["id"]

        postings = client.get(
            f"/api/v1/invoices/{invoice_id}/postings",
            headers=headers,
        )
        assert postings.status_code == 200
        assert [item["id"] for item in postings.json()[:2]] == [
            retry_payload["id"],
            first_payload["id"],
        ]


def test_tally_cloud_connector_claims_and_completes_jobs(tmp_path: Path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        headers = authorization(tokens)

        profile_response = client.post(
            f"/api/v1/organizations/{org_id}/client-profiles",
            json={
                "name": "Neel Tally Connector",
                "accounting_system": "tally",
                "is_default": True,
                "settings": {
                    "company_name": "NEEL ENTERPRISE",
                    "country_code": "IN",
                    "country_name": "India",
                    "default_currency": "INR",
                    "posting_mode": "item_invoice",
                    "voucher_type": "Purchase",
                    "purchase_ledger": "PURCHASES A/C",
                    "tax_ledger": "IGST A/C",
                    "stock_item_name": "PTA SWEEP",
                    "stock_item_hsn": "29173600",
                    "stock_item_uom": "KGS",
                    "tcs_ledger": "TCS",
                    "round_off_ledger": "ROUND OFF",
                    "connection_settings": {
                        "connector_enabled": True,
                        "workspace_id": "neel-prod",
                        "connector_token": "connector-secret",
                        "tally_url": "http://localhost:9000",
                    },
                },
            },
            headers=headers,
        )
        assert profile_response.status_code == 201
        profile_id = profile_response.json()["id"]

        invoice = import_sample_invoice(client, tokens, org_id)
        invoice_id = invoice["id"]
        assert client.post(f"/api/v1/invoices/{invoice_id}/validate", headers=headers).status_code == 200
        assert client.post(f"/api/v1/invoices/{invoice_id}/approve", headers=headers).status_code == 200

        unauthorized = client.post(
            "/api/v1/connectors/tally/jobs/claim",
            json={"workspace_id": "neel-prod"},
        )
        assert unauthorized.status_code == 401

        claimed = client.post(
            "/api/v1/connectors/tally/jobs/claim",
            json={"workspace_id": "neel-prod", "limit": 5},
            headers={"Authorization": "Bearer connector-secret"},
        )
        assert claimed.status_code == 200
        claim_payload = claimed.json()
        assert claim_payload["success"] is True
        assert len(claim_payload["jobs"]) == 1
        job = claim_payload["jobs"][0]
        assert job["client_profile_id"] == profile_id
        assert job["company_name"] == "NEEL ENTERPRISE"
        assert "PTA SWEEP" in job["xml"] or "PURCHASES A/C" in job["xml"]

        duplicate_claim = client.post(
            "/api/v1/connectors/tally/jobs/claim",
            json={"workspace_id": "neel-prod", "limit": 5},
            headers={"Authorization": "Bearer connector-secret"},
        )
        assert duplicate_claim.status_code == 200
        assert duplicate_claim.json()["jobs"] == []

        completed = client.post(
            "/api/v1/connectors/tally/jobs/results",
            json={
                "workspace_id": "neel-prod",
                "results": [
                    {
                        "posting_id": job["posting_id"],
                        "invoice_id": invoice_id,
                        "success": True,
                        "message": "Posted to Tally",
                        "external_id": "tally-voucher-1",
                        "raw": {"created": 1},
                    }
                ],
            },
            headers={"X-SiftEntry-Connector-Token": "connector-secret"},
        )
        assert completed.status_code == 200
        result_payload = completed.json()
        assert result_payload["accepted"] == 1
        assert result_payload["postings"][0]["success"] is True
        assert result_payload["postings"][0]["external_id"] == "tally-voucher-1"

        posted_invoice = client.get(f"/api/v1/invoices/{invoice_id}", headers=headers)
        assert posted_invoice.status_code == 200
        assert posted_invoice.json()["status"] == InvoiceStatus.POSTED.value


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
        assert any(
            message.to_email == "viewer@example.com"
            and "/invite?token=" in message.text_body
            for message in client.app.state.email.outbox
        )

        pending_invitations = client.get(
            f"/api/v1/organizations/{organization_b}/invitations",
            headers=owner_headers,
        )
        assert pending_invitations.status_code == 200
        assert pending_invitations.json()[0]["email"] == "viewer@example.com"

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

        organization_b_members = client.get(
            f"/api/v1/organizations/{organization_b}/members",
            headers=owner_headers,
        )
        assert organization_b_members.status_code == 200
        assert {member["email"] for member in organization_b_members.json()} == {
            "owner@example.com",
            "viewer@example.com",
        }
        assert client.get(
            f"/api/v1/organizations/{organization_b}/members",
            headers=viewer_headers,
        ).status_code == 403

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

        document_response = client.get(
            f"/api/v1/invoices/{uploaded.json()['id']}/document",
            headers=authorization(tokens),
        )
        assert document_response.status_code == 200
        assert document_response.headers["content-type"].startswith("application/pdf")
        assert document_response.content.startswith(b"%PDF")

        cleared = client.delete(
            f"/api/v1/organizations/{org_id}/invoices",
            headers=authorization(tokens),
        )
        assert cleared.status_code == 200
        assert not stored_path.exists()


def test_preview_upload_does_not_persist_invoice_or_pdf(tmp_path: Path):
    import fitz

    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        document = fitz.open()
        page = document.new_page()
        page.insert_text(
            (72, 72),
            "INVOICE INV-200\nSupplier Example\nInvoice Date 19-JUN-2026\nTotal USD 118.00",
        )
        pdf_bytes = document.tobytes()
        document.close()

        uploaded = client.post(
            "/api/v1/invoices/upload",
            params={"organization_id": org_id, "persist": "false"},
            files={"file": ("preview.pdf", pdf_bytes, "application/pdf")},
            headers=authorization(tokens),
        )
        assert uploaded.status_code == 201
        payload = uploaded.json()
        assert payload["id"].startswith("preview-")
        assert payload["source_path"] == ""
        assert payload["invoice_number"] == "INV-200"

        saved = client.get(
            "/api/v1/invoices",
            params={"organization_id": org_id},
            headers=authorization(tokens),
        )
        assert saved.status_code == 200
        assert saved.json() == []
        assert not any((tmp_path / "uploads").rglob("preview.pdf"))
