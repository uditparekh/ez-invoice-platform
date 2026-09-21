"""pkg35C: exact entries, stale previews, transaction races and provenance."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier

import pytest

from siftentry_app.backend.models import ClientProfilePatch, InvoicePatch
from siftentry_app.backend.approval_plans import ApprovalConflict, build_plan
from tests.test_api import (
    make_client,
    bootstrap,
    organization_id,
    authorization,
    _connector_profile_and_invoice,
    _claim,
    _submit_result,
    approve_with_preview,
    _invite_and_accept,
)


def prepared(client):
    owner = bootstrap(client)
    org = organization_id(owner)
    profile, invoice, headers = _connector_profile_and_invoice(client, owner, org)
    response = client.post(f"/api/v1/invoices/{invoice}/validate", headers=headers)
    assert response.status_code == 200
    return org, profile, invoice, headers


def preview(client, invoice, headers):
    response = client.post(
        f"/api/v1/invoices/{invoice}/posting-preview", headers=headers, json={}
    )
    assert response.status_code == 200, response.text
    return response.json()


def approve(client, invoice, headers, plan):
    return client.post(
        f"/api/v1/invoices/{invoice}/approve",
        headers=headers,
        json={
            "client_profile_id": plan["client_profile_id"],
            "preview_hash": plan["preview_hash"],
        },
    )


def test_preview_is_read_only_and_claim_executes_exact_saved_xml(tmp_path):
    with make_client(tmp_path) as client:
        _, profile, invoice, headers = prepared(client)
        repo = client.app.state.repository
        before = repo.get_invoice(invoice).model_dump()
        plan = preview(client, invoice, headers)["plan"]
        assert repo.get_invoice(invoice).model_dump() == before
        assert not plan["blocking_issues"]
        assert "connector-secret" not in str(plan)
        assert [entry["side"] for entry in plan["ledgers"]] == [
            "credit",
            "debit",
            "debit",
        ]
        assert approve(client, invoice, headers, plan).status_code == 200
        frozen = repo.get_approval_plan(invoice)
        assert frozen["version"] == 1 and frozen["approved_by"]
        job = _claim(client).json()["jobs"][0]
        assert job["xml"] == plan["xml"] == frozen["xml"]
        assert job["posting_plan"]["id"] == frozen["id"]
        assert _claim(client).json()["jobs"] == []


def test_no_preview_no_approval_and_legacy_approval_is_not_claimable(tmp_path):
    from siftentry_app.backend.models import InvoiceStatus

    with make_client(tmp_path) as client:
        _, _, invoice, headers = prepared(client)
        assert (
            client.post(
                f"/api/v1/invoices/{invoice}/approve", headers=headers
            ).status_code
            == 409
        )
        client.app.state.repository.set_status(invoice, InvoiceStatus.APPROVED)
        assert _claim(client).json()["jobs"] == []
        assert preview(client, invoice, headers)["requires_reapproval"]


@pytest.mark.parametrize("change", ["invoice", "profile"])
def test_stale_preview_cannot_be_approved(tmp_path, change):
    with make_client(tmp_path) as client:
        org, profile, invoice, headers = prepared(client)
        plan = preview(client, invoice, headers)["plan"]
        if change == "invoice":
            assert (
                client.patch(
                    f"/api/v1/invoices/{invoice}",
                    headers=headers,
                    json={"invoice_number": "REVISED"},
                ).status_code
                == 200
            )
            client.post(f"/api/v1/invoices/{invoice}/validate", headers=headers)
        else:
            repo = client.app.state.repository
            settings = repo.get_client_profile(profile).settings.model_copy(deep=True)
            settings.purchase_ledger = "Different ledger"
            repo.update_client_profile(profile, ClientProfilePatch(settings=settings))
        assert approve(client, invoice, headers, plan).status_code == 409
        assert _claim(client).json()["jobs"] == []
        assert client.app.state.repository.get_approval_plan(invoice) is None


def test_relevant_profile_edit_invalidates_and_reapproval_versions_are_immutable(
    tmp_path,
):
    with make_client(tmp_path) as client:
        _, profile, invoice, headers = prepared(client)
        repo = client.app.state.repository
        assert approve_with_preview(client, invoice, headers).status_code == 200
        old = repo.get_approval_plan(invoice)
        settings = repo.get_client_profile(profile).settings.model_copy(deep=True)
        settings.purchase_ledger = "New purchase ledger"
        repo.update_client_profile(profile, ClientProfilePatch(settings=settings))
        assert repo.get_invoice(invoice).status == "validated"
        assert _claim(client).json()["jobs"] == []
        assert repo.get_approval_plan(invoice) == old
        assert approve_with_preview(client, invoice, headers).status_code == 200
        new = repo.get_approval_plan(invoice)
        assert new["version"] == 2 and new["id"] != old["id"]
        assert "New purchase ledger" in _claim(client).json()["jobs"][0]["xml"]
        with repo._connect() as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) AS n FROM approval_plans WHERE invoice_id = ?",
                    (invoice,),
                ).fetchone()["n"]
                == 2
            )


def test_token_rotation_and_cosmetic_edit_do_not_invalidate(tmp_path):
    with make_client(tmp_path) as client:
        _, profile, invoice, headers = prepared(client)
        repo = client.app.state.repository
        assert approve_with_preview(client, invoice, headers).status_code == 200
        settings = repo.get_client_profile(profile).settings.model_copy(deep=True)
        settings.connection_settings["connector_token"] = "rotated-secret"
        settings.training_profile.extraction_instructions = "New extraction guidance"
        repo.update_client_profile(
            profile,
            ClientProfilePatch(settings=settings, description="New description"),
        )
        assert repo.get_invoice(invoice).status == "approved"
        result = client.post(
            "/api/v1/connectors/tally/jobs/claim",
            json={"workspace_id": "neel-prod"},
            headers={"Authorization": "Bearer rotated-secret"},
        )
        assert len(result.json()["jobs"]) == 1


def test_pending_invoice_edit_revokes_approval_and_tracks_even_opt_out_corrections(
    tmp_path,
):
    with make_client(tmp_path) as client:
        _, _, invoice, headers = prepared(client)
        assert approve_with_preview(client, invoice, headers).status_code == 200
        response = client.patch(
            f"/api/v1/invoices/{invoice}",
            headers=headers,
            json={"invoice_number": "Corrected", "learn_vendor_memory": False},
        )
        assert response.status_code == 200 and response.json()["status"] == "extracted"
        assert _claim(client).json()["jobs"] == []
        fields = client.get(
            f"/api/v1/invoices/{invoice}/review", headers=headers
        ).json()["fields"]
        assert (
            next(field for field in fields if field["field_path"] == "invoice_number")[
                "origin"
            ]
            == "reviewer_confirmed"
        )
        assert (
            next(field for field in fields if field["field_path"] == "total")["origin"]
            == "extracted"
        )


def test_inflight_invoice_cannot_be_edited_or_revalidated_and_plan_survives_profile_edit(
    tmp_path,
):
    with make_client(tmp_path) as client:
        _, profile, invoice, headers = prepared(client)
        repo = client.app.state.repository
        assert approve_with_preview(client, invoice, headers).status_code == 200
        job = _claim(client).json()["jobs"][0]
        assert (
            client.patch(
                f"/api/v1/invoices/{invoice}", headers=headers, json={"total": 10}
            ).status_code
            == 409
        )
        assert (
            client.post(
                f"/api/v1/invoices/{invoice}/validate", headers=headers
            ).status_code
            == 409
        )
        settings = repo.get_client_profile(profile).settings.model_copy(deep=True)
        settings.company_name = "New company"
        repo.update_client_profile(profile, ClientProfilePatch(settings=settings))
        shown = preview(client, invoice, headers)
        assert shown["state"] == "approved" and shown["plan"]["xml"] == job["xml"]
        assert repo.get_invoice(invoice).status == "posting"
        assert _submit_result(client, job, True, "done").json()["accepted"] == 1
        assert (
            client.patch(
                f"/api/v1/invoices/{invoice}", headers=headers, json={"total": 10}
            ).status_code
            == 409
        )


def test_profile_delete_invalidates_pending_plan(tmp_path):
    with make_client(tmp_path) as client:
        _, profile, invoice, headers = prepared(client)
        repo = client.app.state.repository
        assert approve_with_preview(client, invoice, headers).status_code == 200
        repo.delete_client_profile(profile)
        assert repo.get_invoice(invoice).status == "validated"
        assert repo.get_approval_plan(invoice) is not None


def test_simultaneous_approval_has_one_winner(tmp_path):
    with make_client(tmp_path) as client:
        _, _, invoice, headers = prepared(client)
        plan = preview(client, invoice, headers)["plan"]
        barrier = Barrier(2)

        def run(_):
            barrier.wait()
            return approve(client, invoice, headers, plan).status_code

        with ThreadPoolExecutor(2) as pool:
            assert sorted(pool.map(run, range(2))) == [200, 409]
        assert client.app.state.repository.get_approval_plan(invoice)["version"] == 1


@pytest.mark.parametrize("race", ["profile", "invoice"])
def test_edit_vs_claim_never_posts_changed_unapproved_values(tmp_path, race):
    with make_client(tmp_path) as client:
        _, profile, invoice, headers = prepared(client)
        repo = client.app.state.repository
        assert approve_with_preview(client, invoice, headers).status_code == 200
        old = repo.get_approval_plan(invoice)
        barrier = Barrier(2)

        def edit():
            barrier.wait()
            try:
                if race == "invoice":
                    repo.patch_invoice(invoice, InvoicePatch(invoice_number="NEW"))
                else:
                    settings = repo.get_client_profile(profile).settings.model_copy(
                        deep=True
                    )
                    settings.purchase_ledger = "UNAPPROVED LEDGER"
                    repo.update_client_profile(
                        profile, ClientProfilePatch(settings=settings)
                    )
            except ApprovalConflict:
                pass

        def claim():
            barrier.wait()
            return _claim(client).json()["jobs"]

        with ThreadPoolExecutor(2) as pool:
            editing = pool.submit(edit)
            jobs = pool.submit(claim).result()
            editing.result()
        if jobs:
            assert jobs[0]["xml"] == old["xml"]
            assert repo.get_invoice(invoice).status == "posting"
        else:
            assert repo.get_invoice(invoice).status in {"extracted", "validated"}


def test_viewer_can_preview_without_secrets_but_cannot_approve(tmp_path):
    with make_client(tmp_path) as client:
        org, _, invoice, headers = prepared(client)
        _invite_and_accept(client, org, headers, "viewer@example.com", "viewer")
        tokens = client.post(
            "/api/v1/auth/login",
            json={"email": "viewer@example.com", "password": "member-password-is-long"},
        ).json()
        viewer = authorization(tokens)
        plan = preview(client, invoice, viewer)["plan"]
        assert "connector-secret" not in str(plan)
        assert approve(client, invoice, viewer, plan).status_code == 403


@pytest.mark.parametrize(
    "mode", ["accounting_voucher", "item_invoice", "voucher_with_inventory"]
)
def test_all_tally_modes_preview_without_mutating_source(tmp_path, mode):
    with make_client(tmp_path) as client:
        _, profile, invoice, _ = prepared(client)
        repo = client.app.state.repository
        item = repo.get_invoice(invoice)
        settings = repo.get_client_profile(profile)
        settings.settings.posting_mode = mode
        before = deepcopy(item.raw_payload)
        plan = build_plan(item, settings)
        assert not plan["blocking_issues"]
        assert item.raw_payload == before
        assert plan["ledgers"]
        assert bool(plan["inventory"]) == (mode != "accounting_voucher")


def test_raw_tally_result_cannot_bypass_approved_job(tmp_path):
    with make_client(tmp_path) as client:
        _, _, invoice, headers = prepared(client)
        response = client.post(
            f"/api/v1/invoices/{invoice}/posting-results",
            headers=headers,
            json={
                "target": "tally",
                "success": True,
                "dry_run": False,
                "message": "fake",
            },
        )
        assert response.status_code == 409


@pytest.mark.parametrize("bad_value", ["nonfinite", "xml_control"])
def test_invalid_preview_values_fail_clearly(tmp_path, bad_value):
    with make_client(tmp_path) as client:
        _, profile, invoice, _ = prepared(client)
        repo = client.app.state.repository
        item = repo.get_invoice(invoice)
        if bad_value == "nonfinite":
            item.total = float("nan")
        else:
            item.invoice_number = "Invalid\x00number"
        with pytest.raises(ApprovalConflict):
            build_plan(item, repo.get_client_profile(profile))


def test_approval_transaction_rolls_back_when_audit_fails(tmp_path, monkeypatch):
    with make_client(tmp_path) as client:
        _, _, invoice, headers = prepared(client)
        repo = client.app.state.repository
        plan = preview(client, invoice, headers)["plan"]
        original = repo._insert_audit

        def fail(connection, org, item, event, details):
            if event == "invoice.approved":
                raise RuntimeError("simulated audit failure")
            return original(connection, org, item, event, details)

        monkeypatch.setattr(repo, "_insert_audit", fail)
        with pytest.raises(RuntimeError, match="simulated audit failure"):
            approve(client, invoice, headers, plan)
        assert repo.get_invoice(invoice).status == "validated"
        assert repo.get_approval_plan(invoice) is None


def test_currency_mismatch_blocks_approval(tmp_path):
    with make_client(tmp_path) as client:
        _, profile, invoice, headers = prepared(client)
        repo = client.app.state.repository
        settings = repo.get_client_profile(profile).settings.model_copy(deep=True)
        settings.default_currency = "EUR"
        repo.update_client_profile(profile, ClientProfilePatch(settings=settings))
        plan = preview(client, invoice, headers)["plan"]
        assert any("currency" in issue for issue in plan["blocking_issues"])
        assert approve(client, invoice, headers, plan).status_code == 409


def test_approved_plan_cannot_change_destination_or_use_manual_result(tmp_path):
    with make_client(tmp_path) as client:
        _, _, invoice, headers = prepared(client)
        assert approve_with_preview(client, invoice, headers).status_code == 200
        for target in ["tally", "quickbooks"]:
            response = client.post(
                f"/api/v1/invoices/{invoice}/post",
                headers=headers,
                json={"target": target, "dry_run": False},
            )
            assert response.status_code == 409
        response = client.post(
            f"/api/v1/invoices/{invoice}/posting-results",
            headers=headers,
            json={
                "target": "quickbooks",
                "success": True,
                "dry_run": False,
                "message": "fake",
            },
        )
        assert response.status_code == 409
        assert len(_claim(client).json()["jobs"]) == 1
