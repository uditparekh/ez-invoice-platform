"""Security acceptance tests: real routes, isolated data, no production secrets."""
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from siftentry_app.backend.connector_secrets import token_hash, token_matches
from siftentry_app.backend.models import InvoiceCreate, OrganizationRole
from siftentry_app.backend.repository import InvoiceRepository
from siftentry_app.backend.security import hash_password, verify_password, hash_password_reset_token
from siftentry_app.backend.storage import LocalDocumentStorage
from tests.test_api import (make_client, bootstrap, authorization, organization_id,
                            emailed_token, _tally_profile_body, make_text_pdf)
from tests.test_infra_settings import _production_settings


@pytest.mark.parametrize("environment", ["pilot", "staging", "production", "prod", ""])
def test_all_hosted_modes_fail_closed(tmp_path, environment):
    settings = _production_settings(tmp_path, environment=environment, jwt_secret="bad")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        settings.validate_startup()


@pytest.mark.parametrize("environment", ["development", "test", "pilot", "staging", "production"])
def test_tokens_only_delivered_by_email_in_every_mode(tmp_path, environment):
    with make_client(tmp_path) as client:
        owner = bootstrap(client)
        # Exercise response behavior independently of hosted infrastructure.
        client.app.state.settings = replace(client.app.state.settings, environment=environment)
        response = client.post("/api/v1/auth/password-reset/request", json={"email": "owner@example.com"})
        secret = emailed_token(client)
        assert response.status_code == 200 and secret not in response.text
        assert response.json()["reset_token"] is None
        missing = client.post("/api/v1/auth/password-reset/request", json={"email": "absent@example.com"})
        assert missing.json() == response.json()
        invited = client.post(f"/api/v1/organizations/{organization_id(owner)}/invitations",
                              headers=authorization(owner), json={"email": "new@example.com", "role": "viewer"})
        assert invited.status_code == 201
        assert invited.json()["invitation_token"] is None
        assert emailed_token(client, "new@example.com") not in invited.text


def test_client_paths_and_legacy_records_cannot_read_or_delete_host_files(tmp_path):
    sentinel = tmp_path / "private-server-config.txt"
    sentinel.write_text("isolated test sentinel")
    with make_client(tmp_path) as client:
        owner = bootstrap(client)
        org, headers = organization_id(owner), authorization(owner)
        repo = client.app.state.repository
        user = repo.create_user("accountant@example.com", hash_password("test-password-long"), "Accountant")
        repo.create_membership(user.id, org, OrganizationRole.ACCOUNTANT)
        accountant = client.post("/api/v1/auth/login", json={"email": user.email, "password": "test-password-long"}).json()
        for path in (str(sentinel), "../../private-server-config.txt", "/etc/passwd"):
            result = client.post("/api/v1/invoices/import", headers=authorization(accountant),
                                 json={"organization_id": org, "source_file": "invoice.pdf", "source_path": path})
            assert result.status_code == 422
        legacy = repo.create_invoice(InvoiceCreate(organization_id=org, source_file="invoice.pdf", source_path=str(sentinel)))
        assert client.get(f"/api/v1/invoices/{legacy.id}/document", headers=authorization(accountant)).status_code == 404
        assert client.delete(f"/api/v1/organizations/{org}/invoices", headers=headers).status_code == 200
        assert sentinel.read_text() == "isolated test sentinel"


def test_local_storage_rejects_escape_symlinks_and_cross_workspace(tmp_path):
    storage = LocalDocumentStorage(tmp_path / "uploads")
    sentinel = tmp_path / "private.txt"
    sentinel.write_text("keep")
    link = storage.root / "link.pdf"
    link.symlink_to(sentinel)
    for target in (sentinel, link):
        with pytest.raises(ValueError):
            storage.read(target)
        storage.delete(target)
    assert sentinel.read_text() == "keep"
    record = storage.save("org-a", "invoice.pdf", b"%PDF-test")
    with pytest.raises(ValueError):
        storage.read(SimpleNamespace(local_path=record.local_path, organization_id="org-b"))


def test_upload_validates_bytes_size_and_serves_pdf_with_security_headers(tmp_path):
    with make_client(tmp_path, max_upload_bytes=2000) as client:
        owner = bootstrap(client)
        url = f"/api/v1/invoices/upload?organization_id={organization_id(owner)}"
        headers = authorization(owner)
        bad = client.post(url, headers=headers, files={"file": ("invoice.pdf", b"<script>alert(1)</script>", "text/html")})
        assert bad.status_code == 415
        big = client.post(url, headers=headers, files={"file": ("invoice.pdf", b"%PDF-" + b"x" * 2000, "application/pdf")})
        assert big.status_code == 413
        result = client.post(url, headers=headers, files={"file": ("invoice.pdf", make_text_pdf("Invoice TEST-1 Total 100 USD"), "text/html")})
        assert result.status_code == 201
        response = client.get(f"/api/v1/invoices/{result.json()['id']}/document", headers=headers)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["cache-control"] == "no-store"


def test_login_budget_is_atomic_shared_and_does_not_store_identifiers(tmp_path, monkeypatch):
    from siftentry_app.backend.auth_limits import enforce_auth_budget
    from fastapi import HTTPException
    with make_client(tmp_path) as client:
        repo = client.app.state.repository
        other = InvoiceRepository(repo.database_path, repo.database_url)
        monkeypatch.setattr("siftentry_app.backend.auth_limits.time.time", lambda: 1_800_000_010)
        def attempt(index):
            request = SimpleNamespace(client=SimpleNamespace(host=f"peer-{index}"), app=SimpleNamespace(state=SimpleNamespace(repository=repo if index % 2 else other)))
            try:
                enforce_auth_budget(request, "login", "target@example.com", limit=5)
                return 200
            except HTTPException as exc:
                assert exc.headers["Retry-After"]
                return exc.status_code
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(attempt, range(16)))
        assert outcomes.count(200) == 5 and outcomes.count(429) == 11
        with repo._connect() as connection:
            keys = [row["bucket_key"] for row in connection.execute("SELECT bucket_key FROM auth_rate_buckets").fetchall()]
        assert all(len(key) == 64 and "target" not in key for key in keys)


def test_unknown_login_still_checks_password_hash_and_limits_requests(tmp_path, monkeypatch):
    calls = []
    def verifier(password, encoded):
        calls.append(encoded)
        return False
    monkeypatch.setattr("siftentry_app.backend.main.verify_password", verifier)
    with make_client(tmp_path) as client:
        for _ in range(10):
            assert client.post("/api/v1/auth/login", json={"email": "missing@example.com", "password": "long-wrong-password"}).status_code == 401
        blocked = client.post("/api/v1/auth/login", json={"email": "missing@example.com", "password": "long-wrong-password"})
        assert blocked.status_code == 429 and blocked.headers["retry-after"]
        assert len(calls) == 10 and all(calls)


def test_password_reset_is_single_use_under_race_and_revokes_sessions(tmp_path):
    with make_client(tmp_path) as client:
        owner = bootstrap(client)
        repo = client.app.state.repository
        client.post("/api/v1/auth/password-reset/request", json={"email": "owner@example.com"})
        reset = repo.get_password_reset_by_hash(hash_password_reset_token(emailed_token(client)))
        passwords = [hash_password("first-new-password"), hash_password("second-new-password")]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda encoded: repo.consume_password_reset(reset.id, owner["user"]["id"], encoded), passwords))
        assert results.count(True) == 1
        assert repo.get_password_hash(owner["user"]["id"]) == passwords[results.index(True)]
        assert client.get("/api/v1/auth/me", headers=authorization(owner)).status_code == 401
        assert client.post("/api/v1/auth/refresh", json={"refresh_token": owner["refresh_token"]}).status_code == 401


def test_connector_hash_migration_preserves_installation_and_no_hash_is_a_bearer(tmp_path):
    with make_client(tmp_path) as client:
        owner = bootstrap(client)
        org, headers = organization_id(owner), authorization(owner)
        body = _tally_profile_body("Secure Tally", True)
        url = f"/api/v1/organizations/{org}/client-profiles"
        created = client.post(url, headers=headers, json=body)
        assert created.status_code == 201
        profile_id = created.json()["id"]
        repo = client.app.state.repository
        plaintext = body["settings"]["connection_settings"]["connector_token"]
        stored = repo.get_client_profile(profile_id).settings.connection_settings["connector_token"]
        assert stored != plaintext and token_matches(plaintext, stored)
        # Simulate the pre-release database; the next repository startup migrates it.
        with repo._connect() as connection:
            connection.execute("UPDATE client_profiles SET settings_json = ? WHERE id = ?", (json.dumps(body["settings"]), profile_id))
        InvoiceRepository(repo.database_path, repo.database_url)
        for token, expected in ((plaintext, 200), (stored, 401)):
            result = client.post("/api/v1/connectors/tally/diagnostics", json={"workspace_id": "neel-prod"}, headers={"Authorization": "Bearer " + token})
            assert result.status_code == expected
        public = client.get(url, headers=headers)
        assert plaintext not in public.text and stored not in public.text
        reveal = client.get(f"{url}/{profile_id}/connector-credentials", headers=headers)
        assert reveal.json()["connector_token"] == "" and reveal.json()["connector_token_set"]


def test_generated_token_rotation_and_weak_token_rejection(tmp_path):
    with make_client(tmp_path) as client:
        owner = bootstrap(client)
        org, headers = organization_id(owner), authorization(owner)
        endpoint = f"/api/v1/organizations/{org}/connector-token"
        assert client.post(endpoint).status_code == 401
        generated = client.post(endpoint, headers=headers)
        token = generated.json()["connector_token"]
        assert len(token) == 43 and generated.headers["cache-control"] == "no-store"
        body = _tally_profile_body("Secure Tally", True)
        profile_url = f"/api/v1/organizations/{org}/client-profiles"
        for weak in ("a", "password", token_hash(token)):
            body["settings"]["connection_settings"]["connector_token"] = weak
            result = client.post(profile_url, json=body, headers=headers)
            assert result.status_code == 422
            assert result.json() == {"detail": "Generate a new secure connector token (at least 32 ASCII characters)."}
        body["settings"]["connection_settings"]["connector_token"] = token
        profile = client.post(profile_url, json=body, headers=headers).json()
        replacement = client.post(endpoint, headers=headers).json()["connector_token"]
        settings = profile["settings"]
        settings["connection_settings"]["connector_token"] = replacement
        assert client.patch(f"{profile_url}/{profile['id']}", headers=headers, json={"settings": settings}).status_code == 200
        for candidate, expected in ((token, 401), (replacement, 200)):
            assert client.post("/api/v1/connectors/tally/diagnostics", json={"workspace_id": "neel-prod"}, headers={"Authorization": "Bearer " + candidate}).status_code == expected


def test_security_migration_expires_existing_links_and_sessions_only_once(tmp_path):
    with make_client(tmp_path) as client:
        owner = bootstrap(client)
        repo = client.app.state.repository
        reset = repo.create_password_reset(owner["user"]["id"], "old-reset-hash", datetime.now(timezone.utc) + timedelta(hours=1))
        with repo._connect() as connection:
            connection.execute("DELETE FROM security_migrations WHERE name = ?", ("20260924_revoke_exposed_auth_links",))
        InvoiceRepository(repo.database_path, repo.database_url)
        assert repo.get_password_reset_by_hash("old-reset-hash").used_at is not None
        assert client.get("/api/v1/auth/me", headers=authorization(owner)).status_code == 401
        fresh = client.post("/api/v1/auth/login", json={"email": "owner@example.com", "password": "correct-horse-battery-staple"}).json()
        InvoiceRepository(repo.database_path, repo.database_url)
        assert client.get("/api/v1/auth/me", headers=authorization(fresh)).status_code == 200


def test_accountant_cannot_change_or_omit_connector_destinations(tmp_path):
    with make_client(tmp_path) as client:
        owner = bootstrap(client)
        org, headers = organization_id(owner), authorization(owner)
        repo = client.app.state.repository
        user = repo.create_user("editor@example.com", hash_password("editor-password-long"), "Editor")
        repo.create_membership(user.id, org, OrganizationRole.ACCOUNTANT)
        editor = client.post("/api/v1/auth/login", json={"email": user.email, "password": "editor-password-long"}).json()
        body = _tally_profile_body("Protected destination", True)
        body["settings"]["connection_settings"]["connector_url"] = "http://127.0.0.1:8765"
        url = f"/api/v1/organizations/{org}/client-profiles"
        profile = client.post(url, headers=headers, json=body).json()
        assert client.post(f"/api/v1/organizations/{org}/connector-token", headers=authorization(editor)).status_code == 403
        for remove in (False, True):
            settings = json.loads(json.dumps(profile["settings"]))
            if remove:
                settings["connection_settings"].pop("connector_url")
            else:
                settings["connection_settings"]["connector_url"] = "https://attacker.invalid"
            response = client.patch(f"{url}/{profile['id']}", headers=authorization(editor), json={"settings": settings})
            assert response.status_code == 403
        # Ordinary accounting edits still preserve the protected settings/hash.
        response = client.patch(f"{url}/{profile['id']}", headers=authorization(editor),
                                json={"description": "Permitted edit", "settings": profile["settings"]})
        assert response.status_code == 200


def test_legacy_push_adapter_never_transmits_a_credential_hash(tmp_path, monkeypatch):
    from siftentry_app.backend.adapters import TallyAdapter
    from tests.test_api import _connector_profile_and_invoice
    with make_client(tmp_path) as client:
        owner = bootstrap(client)
        profile, invoice, _ = _connector_profile_and_invoice(client, owner, organization_id(owner))
        def forbidden(*args, **kwargs):
            raise AssertionError("Legacy outbound transport must not run")
        monkeypatch.setattr("siftentry_app.tally_integration.send_to_tally", forbidden)
        repo = client.app.state.repository
        result = TallyAdapter().post(repo.get_invoice(invoice), dry_run=True, client_profile=repo.get_client_profile(profile))
        assert result.success is False
        assert "Windows connector" in result.message
