from pathlib import Path
import base64
import hashlib
import sqlite3
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from siftentry_app.backend.demo_seed import (
    PUBLIC_DEMO_EMAIL,
    PUBLIC_DEMO_FALLBACK_ORGANIZATION,
    PUBLIC_DEMO_ORGANIZATION,
)
from siftentry_app.backend.domain import legacy_payload_to_invoice
from siftentry_app.backend.main import create_app
from siftentry_app.backend.models import (
    InvoiceCreate,
    InvoiceStatus,
    OrganizationCreate,
    OrganizationRole,
)
from siftentry_app.backend.security import hash_password
from siftentry_app.backend.settings import ApiSettings

from .test_domain import sample_legacy_payload


def _database_url_for(tmp_path: Path) -> str:
    """SQLite per tmp_path by default; a fresh PostgreSQL database per test
    when SIFTENTRY_TEST_DATABASE_URL is set (e.g. postgresql://root@/postgres).
    Lets the ENTIRE suite run against both engines."""
    import os
    import uuid

    base = os.environ.get("SIFTENTRY_TEST_DATABASE_URL", "").strip()
    if not base:
        return f"sqlite:///{tmp_path / 'api.db'}"
    dbname = f"siftentry_test_{uuid.uuid4().hex[:12]}"
    from urllib.parse import urlparse

    parsed = urlparse(base)
    return base.replace(parsed.path or "/postgres", f"/{dbname}", 1)


def make_client(tmp_path: Path, **overrides) -> TestClient:
    settings_data = {
        "database_url": _database_url_for(tmp_path),
        "database_path": tmp_path / "api.db",
        "upload_directory": tmp_path / "uploads",
        "max_upload_bytes": 2 * 1024 * 1024,
        "cors_origins": ("http://localhost:3000",),
        "app_base_url": "http://testserver",
        "jwt_secret": "test-secret-that-is-not-used-in-production",
        "access_token_minutes": 5,
        "refresh_token_days": 2,
        "allow_dev_bootstrap": True,
        "environment": "test",
        "email_provider": "memory",
    }
    settings_data.update(overrides)
    app = create_app(
        ApiSettings(**settings_data)
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


def make_text_pdf(text: str) -> bytes:
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text, fontsize=10)
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


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

        ai_status = client.get("/api/v1/system/ai-extraction", headers=headers)
        assert ai_status.status_code == 200
        assert ai_status.json()["provider"] == "profile_context"
        assert ai_status.json()["configured"] is True
        assert ai_status.json()["live_provider"] is False

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

        review = client.get(
            f"/api/v1/invoices/{invoice_id}/review",
            headers=headers,
        )
        assert review.status_code == 200
        review_body = review.json()
        assert review_body["invoice_id"] == invoice_id
        assert review_body["overall_score"] > 0
        assert {field["field_path"] for field in review_body["fields"]} >= {
            "invoice_number",
            "supplier.name",
            "total",
            "lines",
        }
        assert review_body["detected"]["currency"] == "INR"

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


def test_public_demo_is_seeded_once_and_remains_read_only(tmp_path: Path):
    with make_client(tmp_path) as client:
        original = bootstrap(
            client,
            email="demo@siftentry.com",
            password="existing-demo-password",
            organization_name="Public Product Tour",
        )
        first = client.post("/api/v1/auth/demo")
        assert first.status_code == 200
        tokens = first.json()
        assert tokens["user"]["id"] == original["user"]["id"]
        assert tokens["user"]["email"] == "demo@siftentry.com"
        assert len(tokens["user"]["memberships"]) == 1
        membership = tokens["user"]["memberships"][0]
        assert membership["role"] == "viewer"

        headers = authorization(tokens)
        org_id = membership["organization_id"]
        invoices = client.get(
            "/api/v1/invoices",
            params={"organization_id": org_id},
            headers=headers,
        )
        assert invoices.status_code == 200
        invoice_rows = invoices.json()
        assert {row["invoice_number"] for row in invoice_rows} == {
            "DEMO-QB-1001",
            "DEMO-ZOHO-1002",
        }
        assert {row["status"] for row in invoice_rows} == {"posted"}
        assert {row["currency"] for row in invoice_rows} == {"USD"}
        assert all(
            row["source_path"].startswith("synthetic-demo/")
            for row in invoice_rows
        )
        assert {row["supplier"]["name"] for row in invoice_rows} == {
            "Northwind Office Supply Inc.",
            "BrightPath Cloud Services LLC",
        }

        organization = client.get(
            "/api/v1/organizations",
            headers=headers,
        )
        assert organization.status_code == 200
        assert organization.json()[0]["default_currency"] == "USD"

        for invoice in invoice_rows:
            activity = client.get(
                f"/api/v1/invoices/{invoice['id']}/activity",
                headers=headers,
            )
            assert activity.status_code == 200
            assert any(
                event["type"] == "posting_success"
                for event in activity.json()["events"]
            )

        denied = client.post(
            "/api/v1/invoices/import",
            json={
                "organization_id": org_id,
                "source_file": "not-allowed.pdf",
            },
            headers=headers,
        )
        assert denied.status_code == 403

        password_still_works = client.post(
            "/api/v1/auth/login",
            json={
                "email": "demo@siftentry.com",
                "password": "existing-demo-password",
            },
        )
        assert password_still_works.status_code == 200
        assert password_still_works.json()["user"]["id"] == original["user"]["id"]

        second = client.post("/api/v1/auth/demo")
        assert second.status_code == 200
        second_headers = authorization(second.json())
        seeded_again = client.get(
            "/api/v1/invoices",
            params={"organization_id": org_id},
            headers=second_headers,
        )
        assert seeded_again.status_code == 200
        assert {row["id"] for row in seeded_again.json()} == {
            row["id"] for row in invoice_rows
        }


def test_public_demo_never_reuses_same_named_customer_workspace(tmp_path: Path):
    with make_client(tmp_path) as client:
        owner = bootstrap(
            client,
            organization_name=PUBLIC_DEMO_ORGANIZATION,
        )
        owner_org_id = organization_id(owner, PUBLIC_DEMO_ORGANIZATION)

        demo = client.post("/api/v1/auth/demo")
        assert demo.status_code == 200
        demo_membership = demo.json()["user"]["memberships"][0]
        demo_org_id = demo_membership["organization_id"]
        assert demo_org_id != owner_org_id
        assert (
            demo_membership["organization_name"]
            == PUBLIC_DEMO_FALLBACK_ORGANIZATION
        )

        owner_invoices = client.get(
            "/api/v1/invoices",
            params={"organization_id": owner_org_id},
            headers=authorization(owner),
        )
        assert owner_invoices.status_code == 200
        assert owner_invoices.json() == []
        assert {
            member.email
            for member in client.app.state.repository.list_organization_members(
                owner_org_id
            )
        } == {"owner@example.com"}


def test_public_demo_repairs_legacy_shared_workspace_without_touching_real_data(
    tmp_path: Path,
):
    with make_client(tmp_path) as client:
        owner = bootstrap(client, organization_name="Owner Workspace")
        owner_org_id = organization_id(owner, "Owner Workspace")
        repository = client.app.state.repository
        demo_user = repository.create_user(
            email=PUBLIC_DEMO_EMAIL,
            password_hash=hash_password("legacy-demo-password"),
            full_name="SiftEntry Demo",
        )
        repository.create_membership(
            demo_user.id,
            owner_org_id,
            OrganizationRole.VIEWER,
        )
        primary_demo_org = repository.create_organization(
            OrganizationCreate(
                name=PUBLIC_DEMO_ORGANIZATION,
                legal_names=["SiftEntry Demo Operations Inc."],
                default_currency="USD",
            )
        )
        extra_demo_org = repository.create_organization(
            OrganizationCreate(
                name=PUBLIC_DEMO_FALLBACK_ORGANIZATION,
                legal_names=["SiftEntry Demo Operations Inc."],
                default_currency="USD",
            )
        )
        repository.create_membership(
            demo_user.id,
            primary_demo_org.id,
            OrganizationRole.VIEWER,
        )
        repository.create_membership(
            demo_user.id,
            extra_demo_org.id,
            OrganizationRole.VIEWER,
        )
        repository.create_invoice(
            InvoiceCreate(
                organization_id=owner_org_id,
                source_file="northwind-office-supply-demo.pdf",
                source_path="synthetic-demo/northwind-office-supply-demo.pdf",
                invoice_number="DEMO-QB-1001",
                raw_payload={"demo": True, "demo_seed_version": 1},
            )
        )
        repository.create_invoice(
            InvoiceCreate(
                organization_id=owner_org_id,
                source_file="real-customer-invoice.pdf",
                source_path="uploads/real-customer-invoice.pdf",
                invoice_number="REAL-1001",
            )
        )

        repaired = client.post("/api/v1/auth/demo")
        assert repaired.status_code == 200
        membership = repaired.json()["user"]["memberships"]
        assert len(membership) == 1
        assert membership[0]["organization_id"] == primary_demo_org.id
        assert membership[0]["role"] == "viewer"
        assert repository.get_membership(demo_user.id, owner_org_id) is None
        assert repository.get_membership(demo_user.id, extra_demo_org.id) is None

        owner_invoices = client.get(
            "/api/v1/invoices",
            params={"organization_id": owner_org_id},
            headers=authorization(owner),
        )
        assert owner_invoices.status_code == 200
        assert {
            invoice["invoice_number"] for invoice in owner_invoices.json()
        } == {"REAL-1001"}

        demo_invoices = client.get(
            "/api/v1/invoices",
            params={"organization_id": membership[0]["organization_id"]},
            headers=authorization(repaired.json()),
        )
        assert demo_invoices.status_code == 200
        assert {
            invoice["invoice_number"] for invoice in demo_invoices.json()
        } == {"DEMO-QB-1001", "DEMO-ZOHO-1002"}


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


def test_client_profile_training_profile_and_sample_upload(tmp_path: Path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        headers = authorization(tokens)

        created = client.post(
            f"/api/v1/organizations/{org_id}/client-profiles",
            json={
                "name": "Neel Tally onboarding",
                "accounting_system": "tally",
                "description": "Training profile for client invoice formats.",
                "settings": {
                    "company_name": "NEEL ENTERPRISE",
                    "country_code": "IN",
                    "country_name": "India",
                    "default_currency": "INR",
                    "training_profile": {
                        "business_process": "inbound_ap",
                        "invoice_volume": "100 invoices/month",
                        "expected_fields": [
                            "invoice_number",
                            "supplier",
                            "total",
                            "line_items",
                            "hsn_sac",
                        ],
                        "extraction_instructions": (
                            "Use GST invoice totals and keep IGST separate."
                        ),
                        "validation_rules": [
                            "Total must equal taxable value plus IGST.",
                        ],
                    },
                },
            },
            headers=headers,
        )
        assert created.status_code == 201
        profile = created.json()
        assert profile["settings"]["training_profile"]["invoice_volume"] == (
            "100 invoices/month"
        )
        assert "hsn_sac" in profile["settings"]["training_profile"]["expected_fields"]

        uploaded = client.post(
            f"/api/v1/organizations/{org_id}/client-profiles/{profile['id']}/training-samples",
            files={
                "file": (
                    "client-sample.pdf",
                    b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF",
                    "application/pdf",
                )
            },
            data={"notes": "First GST sample from client", "sample_type": "invoice"},
            headers=headers,
        )
        assert uploaded.status_code == 200
        training = uploaded.json()["settings"]["training_profile"]
        assert training["onboarding_status"] == "samples_added"
        assert training["sample_invoices"][0]["filename"] == "client-sample.pdf"
        assert training["sample_invoices"][0]["notes"] == (
            "First GST sample from client"
        )
        assert Path(training["sample_invoices"][0]["stored_path"]).exists()


def test_client_profile_recommend_settings_from_onboarding_context(tmp_path: Path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        headers = authorization(tokens)

        created = client.post(
            f"/api/v1/organizations/{org_id}/client-profiles",
            json={
                "name": "Neel GST item invoice",
                "accounting_system": "tally",
                "description": "India GST purchase invoices for TallyPrime.",
                "settings": {
                    "company_name": "NEEL ENTERPRISE",
                    "purchase_ledger": "PURCHASES A/C",
                    "voucher_type": "Purchase",
                    "training_profile": {
                        "business_process": "inbound_ap",
                        "accounting_exports": ["tally"],
                        "extraction_instructions": (
                            "Invoices have GSTIN, HSN/SAC, stock item, quantity and UOM."
                        ),
                        "posting_expectations": (
                            "Use Tally Item Invoice with IGST, TCS, round-off and godown."
                        ),
                        "sample_invoices": [
                            {
                                "filename": "Digital Signed (1).pdf",
                                "notes": "Client sample includes IGST and HSN 29173600.",
                            }
                        ],
                    },
                },
            },
            headers=headers,
        )
        assert created.status_code == 201
        profile = created.json()

        recommended = client.post(
            f"/api/v1/organizations/{org_id}/client-profiles/{profile['id']}/recommend-settings",
            headers=headers,
        )
        assert recommended.status_code == 200
        settings = recommended.json()["settings"]
        assert settings["country_code"] == "IN"
        assert settings["default_currency"] == "INR"
        assert settings["tax_mode"] == "gst_igst"
        assert settings["posting_mode"] == "item_invoice"
        assert (
            settings["training_profile"]["onboarding_status"]
            == "recommendations_generated"
        )
        missing = settings["metadata"]["recommendation_missing_fields"]
        assert "Exact IGST ledger name" in missing
        assert "Exact Tally UOM" in missing


def test_client_profile_submit_review_and_activate_tally_profile(tmp_path: Path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        headers = authorization(tokens)

        created = client.post(
            f"/api/v1/organizations/{org_id}/client-profiles",
            json={
                "name": "Neel Item Invoice",
                "accounting_system": "tally",
                "settings": {
                    "company_name": "NEEL ENTERPRISE",
                    "country_code": "IN",
                    "country_name": "India",
                    "default_currency": "INR",
                    "tax_mode": "gst_igst",
                    "posting_mode": "item_invoice",
                    "voucher_type": "Purchase",
                    "purchase_ledger": "PURCHASES A/C",
                    "tax_ledger": "IGST A/C",
                    "tcs_ledger": "TCS",
                    "round_off_ledger": "ROUND OFF",
                    "stock_item_name": "PTA SWEEP",
                    "stock_item_hsn": "29173600",
                    "stock_item_uom": "KGS",
                    "godown_name": "Main Location",
                    "tax_settings": {"igst_ledger": "IGST A/C"},
                    "training_profile": {
                        "business_process": "inbound_ap",
                        "posting_expectations": (
                            "Tally Item Invoice, IGST separate, TCS, round-off, godown."
                        ),
                        "extraction_instructions": (
                            "Use supplier GST invoice totals and preserve item HSN."
                        ),
                    },
                },
            },
            headers=headers,
        )
        assert created.status_code == 201
        profile = created.json()

        submitted = client.post(
            f"/api/v1/organizations/{org_id}/client-profiles/{profile['id']}/submit-review",
            headers=headers,
        )
        assert submitted.status_code == 200
        assert (
            submitted.json()["settings"]["training_profile"]["onboarding_status"]
            == "ready_for_admin_review"
        )

        activated = client.post(
            f"/api/v1/organizations/{org_id}/client-profiles/{profile['id']}/activate",
            headers=headers,
        )
        assert activated.status_code == 200
        body = activated.json()
        assert body["settings"]["training_profile"]["onboarding_status"] == "active"
        assert body["settings"]["metadata"]["activated_by"] == "owner@example.com"


def test_client_profile_activation_blocks_missing_tally_item_fields(tmp_path: Path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        headers = authorization(tokens)

        created = client.post(
            f"/api/v1/organizations/{org_id}/client-profiles",
            json={
                "name": "Incomplete Tally profile",
                "accounting_system": "tally",
                "settings": {
                    "company_name": "NEEL ENTERPRISE",
                    "country_code": "IN",
                    "country_name": "India",
                    "default_currency": "INR",
                    "tax_mode": "gst_igst",
                    "posting_mode": "item_invoice",
                    "voucher_type": "Purchase",
                },
            },
            headers=headers,
        )
        assert created.status_code == 201
        profile = created.json()

        activated = client.post(
            f"/api/v1/organizations/{org_id}/client-profiles/{profile['id']}/activate",
            headers=headers,
        )
        assert activated.status_code == 409
        codes = {issue["code"] for issue in activated.json()["detail"]["issues"]}
        assert "tally_purchase_ledger_missing" in codes
        assert "tally_stock_item_missing" in codes
        assert "tally_stock_uom_missing" in codes


def test_ai_assisted_upload_uses_default_training_profile(tmp_path: Path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        headers = authorization(tokens)

        created = client.post(
            f"/api/v1/organizations/{org_id}/client-profiles",
            json={
                "name": "Neel Tally GST profile",
                "accounting_system": "tally",
                "description": "Default profile for Indian GST purchase invoices.",
                "is_default": True,
                "settings": {
                    "company_name": "NEEL ENTERPRISE",
                    "country_code": "IN",
                    "country_name": "India",
                    "default_currency": "INR",
                    "invoice_format": "gst_einvoice",
                    "tax_mode": "gst_igst",
                    "direction": "inbound",
                    "purchase_ledger": "PURCHASES A/C",
                    "tax_ledger": "IGST A/C",
                    "tcs_ledger": "TCS",
                    "round_off_ledger": "ROUND OFF",
                    "stock_item_name": "PTA SWEEP",
                    "stock_item_hsn": "29173600",
                    "stock_item_uom": "KGS",
                    "godown_name": "Main Location",
                    "item_mappings": [
                        {
                            "source_description_contains": "terephthalic",
                            "source_hsn_sac": "29173600",
                            "target_item_name": "PTA SWEEP",
                            "target_uom": "KGS",
                            "purchase_ledger": "PURCHASES A/C",
                            "tax_ledger": "IGST A/C",
                            "metadata": {"category": "Materials", "gl_code": "PURCHASES A/C"},
                        }
                    ],
                    "training_profile": {
                        "business_process": "inbound_ap",
                        "expected_fields": [
                            "invoice_number",
                            "supplier",
                            "invoice_date",
                            "currency",
                            "total",
                            "line_items",
                            "hsn_sac",
                        ],
                        "extraction_instructions": (
                            "Treat Indian GST totals, IGST, TCS, and round-off as posting lines."
                        ),
                        "validation_rules": [
                            "GST ledgers should remain separate from purchase ledger.",
                        ],
                        "posting_expectations": "Create a Tally item invoice where item rules are available.",
                    },
                },
            },
            headers=headers,
        )
        assert created.status_code == 201
        profile = created.json()

        pdf_bytes = make_text_pdf(
            "\n".join(
                [
                    "TAX INVOICE",
                    "Invoice No. 2620002662",
                    "Invoice Date 10-Jun-2026",
                    "Supplier MADELIN ENTERPRISES PRIVATE LIMITED",
                    "Description PURIFIED TEREPHTHALIC ACID",
                    "HSN/SAC 29173600 Quantity 1600 KGS Rate 329.18 Amount 526680.00",
                    "IGST A/C 107232.00",
                    "Total INR 633912.00",
                ]
            )
        )

        uploaded = client.post(
            f"/api/v1/invoices/upload?organization_id={org_id}&parser_mode=ai_assisted&persist=false",
            files={"file": ("gst-sample.pdf", pdf_bytes, "application/pdf")},
            headers=headers,
        )
        assert uploaded.status_code == 201
        invoice = uploaded.json()
        document = invoice["raw_payload"]["INVOICE"]["DOCUMENT"]
        account_profile = invoice["raw_payload"]["INVOICE"]["ACCOUNTING PROFILE"]

        assert invoice["parser"] == "AI/OCR assisted"
        assert invoice["currency"] == "INR"
        assert document["AI/OCR MODE"] == "profile_context_v1"
        assert document["AI/OCR PROVIDER"] == "profile_context"
        assert document["AI/OCR CONFIGURED"] is True
        assert document["AI PARSER CONTEXT"]["profile_id"] == profile["id"]
        assert document["PARSER EVALUATION"]["profile_name"] == "Neel Tally GST profile"
        assert account_profile["PURCHASE LEDGER"] == "PURCHASES A/C"
        assert account_profile["TCS LEDGER"] == "TCS"
        assert account_profile["ROUND OFF LEDGER"] == "ROUND OFF"


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


def test_tally_connector_heartbeat_and_status(tmp_path: Path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        headers = authorization(tokens)

        profile_response = client.post(
            f"/api/v1/organizations/{org_id}/client-profiles",
            json={
                "name": "Neel Tally Status",
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
                        "workspace_id": "neel-status",
                        "connector_token": "status-secret",
                        "tally_url": "http://localhost:9000",
                    },
                },
            },
            headers=headers,
        )
        assert profile_response.status_code == 201
        profile_id = profile_response.json()["id"]

        # Before any connector activity: configured but never seen.
        initial = client.get(
            f"/api/v1/organizations/{org_id}/connectors/tally/status",
            headers=headers,
        )
        assert initial.status_code == 200
        initial_payload = initial.json()
        assert initial_payload["organization_id"] == org_id
        entry = next(
            item
            for item in initial_payload["statuses"]
            if item["client_profile_id"] == profile_id
        )
        assert entry["connector_configured"] is True
        assert entry["connected"] is False
        assert entry["last_seen_at"] is None
        assert entry["tally_company"] == "NEEL ENTERPRISE"

        # Heartbeat endpoint rejects a missing/wrong token.
        assert (
            client.post(
                "/api/v1/connectors/tally/heartbeat",
                json={"workspace_id": "neel-status"},
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/v1/connectors/tally/heartbeat",
                json={"workspace_id": "neel-status"},
                headers={"Authorization": "Bearer wrong-token"},
            ).status_code
            == 401
        )

        # A valid heartbeat (Tally down) marks the connector online.
        heartbeat = client.post(
            "/api/v1/connectors/tally/heartbeat",
            json={
                "workspace_id": "neel-status",
                "connector_host": "ACCOUNTS-PC",
                "connector_version": "0.3.0",
                "tally_detected": False,
            },
            headers={"Authorization": "Bearer status-secret"},
        )
        assert heartbeat.status_code == 200
        assert heartbeat.json()["success"] is True

        after_heartbeat = client.get(
            f"/api/v1/organizations/{org_id}/connectors/tally/status",
            headers=headers,
        )
        entry = next(
            item
            for item in after_heartbeat.json()["statuses"]
            if item["client_profile_id"] == profile_id
        )
        assert entry["connected"] is True
        assert entry["connector_host"] == "ACCOUNTS-PC"
        assert entry["connector_version"] == "0.3.0"
        assert entry["tally_detected"] is False

        # A claim call also refreshes the heartbeat and implies Tally is up.
        claimed = client.post(
            "/api/v1/connectors/tally/jobs/claim",
            json={
                "workspace_id": "neel-status",
                "limit": 5,
                "connector_host": "ACCOUNTS-PC",
                "connector_version": "0.3.0",
            },
            headers={"Authorization": "Bearer status-secret"},
        )
        assert claimed.status_code == 200

        after_claim = client.get(
            f"/api/v1/organizations/{org_id}/connectors/tally/status",
            headers=headers,
        )
        entry = next(
            item
            for item in after_claim.json()["statuses"]
            if item["client_profile_id"] == profile_id
        )
        assert entry["connected"] is True
        assert entry["tally_detected"] is True

        # The status endpoint requires an authenticated member.
        assert (
            client.get(
                f"/api/v1/organizations/{org_id}/connectors/tally/status"
            ).status_code
            == 401
        )


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
        payload = uploaded.json()
        stored_path = Path(payload["source_path"])
        assert stored_path.exists()
        retention = payload["document_retention"]
        assert retention["retained"] is True
        assert retention["retention_policy"] == "review_window"
        assert retention["retention_until"]
        assert retention["sha256_hash"] == hashlib.sha256(pdf_bytes).hexdigest()
        assert retention["size_bytes"] == len(pdf_bytes)

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


def test_inbound_email_intake_uses_shared_invoice_processing(tmp_path: Path):
    secret = "email-secret-with-enough-randomness"
    with make_client(tmp_path, inbound_email_secret=secret) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        pdf_bytes = make_text_pdf(
            "INVOICE INV-EMAIL-1\nSupplier Email Vendor\nInvoice Date 20-JUN-2026\nTotal USD 224.00"
        )
        body = {
            "organization_id": org_id,
            "from_email": "ap@supplier.example",
            "to_email": "invoices@siftentry.example",
            "subject": "Invoice INV-EMAIL-1",
            "message_id": "<email-1@example>",
            "attachments": [
                {
                    "filename": "email-invoice.pdf",
                    "content_type": "application/pdf",
                    "content_base64": base64.b64encode(pdf_bytes).decode("ascii"),
                }
            ],
        }

        denied = client.post(
            "/api/v1/inbound/email",
            json=body,
            headers={"X-SiftEntry-Inbound-Secret": "wrong"},
        )
        assert denied.status_code == 403

        accepted = client.post(
            "/api/v1/inbound/email",
            json=body,
            headers={"X-SiftEntry-Inbound-Secret": secret},
        )
        assert accepted.status_code == 202
        payload = accepted.json()
        assert payload["accepted"] == 1
        assert payload["rejected"] == 0
        invoice = payload["invoices"][0]
        assert invoice["invoice_number"] == "INV-EMAIL-1"
        assert invoice["raw_payload"]["ingestion"]["channel"] == "email"
        assert invoice["raw_payload"]["ingestion"]["from_email"] == "ap@supplier.example"
        assert invoice["document_retention"]["retained"] is True
        assert invoice["document_retention"]["sha256_hash"] == hashlib.sha256(pdf_bytes).hexdigest()
        assert Path(invoice["source_path"]).exists()

        queue = client.get(
            "/api/v1/invoices",
            params={"organization_id": org_id},
            headers=authorization(tokens),
        )
        assert queue.status_code == 200
        assert [item["invoice_number"] for item in queue.json()] == ["INV-EMAIL-1"]


def test_expired_pdf_cleanup_keeps_invoice_history(tmp_path: Path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        headers = authorization(tokens)
        pdf_bytes = make_text_pdf(
            "INVOICE INV-RET-1\nSupplier Example\nInvoice Date 19-JUN-2026\nTotal USD 118.00"
        )

        uploaded = client.post(
            "/api/v1/invoices/upload",
            params={"organization_id": org_id},
            files={"file": ("retained.pdf", pdf_bytes, "application/pdf")},
            headers=headers,
        )
        assert uploaded.status_code == 201
        payload = uploaded.json()
        invoice_id = payload["id"]
        file_id = payload["document_retention"]["file_id"]
        stored_path = Path(payload["source_path"])
        assert stored_path.exists()

        # Force-expire the retained file directly in whichever engine is active.
        from siftentry_app.backend import db as _db

        expired_at = datetime(2000, 1, 1, tzinfo=timezone.utc).isoformat()
        test_pg_url = __import__("os").environ.get("SIFTENTRY_TEST_DATABASE_URL", "")
        if test_pg_url:
            repo = client.app.state.repository
            with repo._connect() as connection:
                connection.execute(
                    "UPDATE invoice_files SET retention_until = ? WHERE id = ?",
                    (expired_at, file_id),
                )
        else:
            with sqlite3.connect(tmp_path / "api.db") as connection:
                connection.execute(
                    "UPDATE invoice_files SET retention_until = ? WHERE id = ?",
                    (expired_at, file_id),
                )
        assert _db  # imported for engine-awareness documentation

        cleanup = client.post(
            f"/api/v1/organizations/{org_id}/storage/cleanup",
            headers=headers,
        )
        assert cleanup.status_code == 200
        assert cleanup.json()["expired_files"] == 1
        assert cleanup.json()["deleted_files"] == 1
        assert not stored_path.exists()

        missing_document = client.get(
            f"/api/v1/invoices/{invoice_id}/document",
            headers=headers,
        )
        assert missing_document.status_code == 404

        retained_invoice = client.get(
            f"/api/v1/invoices/{invoice_id}",
            headers=headers,
        )
        assert retained_invoice.status_code == 200
        retained_payload = retained_invoice.json()
        assert retained_payload["invoice_number"] == "INV-RET-1"
        assert retained_payload["source_path"] == ""
        assert retained_payload["document_retention"]["retained"] is False
        assert retained_payload["document_retention"]["deleted_at"]


def test_client_profile_extended_pdf_retention(tmp_path: Path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        headers = authorization(tokens)
        profile_response = client.post(
            f"/api/v1/organizations/{org_id}/client-profiles",
            json={
                "name": "Paid storage pilot",
                "accounting_system": "quickbooks",
                "description": "Profile with paid PDF retention enabled.",
                "settings": {
                    "company_name": "Example Client",
                    "pdf_retention_policy": "extended_90_days",
                    "pdf_retention_days": 30,
                    "paid_pdf_storage": True,
                },
            },
            headers=headers,
        )
        assert profile_response.status_code == 201
        profile_id = profile_response.json()["id"]
        pdf_bytes = make_text_pdf(
            "INVOICE INV-RET-2\nSupplier Example\nInvoice Date 19-JUN-2026\nTotal USD 118.00"
        )

        uploaded = client.post(
            "/api/v1/invoices/upload",
            params={"organization_id": org_id, "client_profile_id": profile_id},
            files={"file": ("paid-retention.pdf", pdf_bytes, "application/pdf")},
            headers=headers,
        )
        assert uploaded.status_code == 201
        retention = uploaded.json()["document_retention"]
        assert retention["retained"] is True
        assert retention["retention_policy"] == "extended_90_days"
        retention_until = datetime.fromisoformat(retention["retention_until"])
        assert (retention_until - datetime.now(timezone.utc)).days >= 89


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
