"""Master snapshots stay tenant/company-bound and never change posting state."""

from copy import deepcopy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_api import (
    make_client,
    bootstrap,
    organization_id,
    authorization,
    _tally_profile_body,
    CONNECTOR_HEADERS,
    _invite_and_accept,
)


def setup(client):
    owner = bootstrap(client)
    org, headers = organization_id(owner), authorization(owner)
    profile = client.post(
        f"/api/v1/organizations/{org}/client-profiles",
        headers=headers,
        json=_tally_profile_body("Tally", True),
    ).json()
    return (
        org,
        headers,
        profile,
        f"/api/v1/organizations/{org}/client-profiles/{profile['id']}/tally-masters",
    )


def begin(client):
    result = client.post(
        "/api/v1/connectors/tally/masters/begin",
        headers=CONNECTOR_HEADERS,
        json={"workspace_id": "neel-prod"},
    )
    assert result.status_code == 200, result.text
    return result.json()["ticket"]


def upload(ticket):
    return {
        "workspace_id": "neel-prod",
        "ticket": ticket,
        "company": {"name": "NEEL ENTERPRISE", "guid": "company-guid"},
        "masters": {
            kind: [{"name": name} for name in names]
            for kind, names in {
                "ledgers": ["PURCHASES A/C", "INPUT TAX"],
                "stock_items": ["Material"],
                "units": ["EA"],
                "godowns": [],
                "voucher_types": ["Purchase"],
            }.items()
        },
    }


def submit(client, body):
    return client.post(
        "/api/v1/connectors/tally/masters/submit", headers=CONNECTOR_HEADERS, json=body
    )


def test_empty_workspace_sync_and_explicit_confirmation_are_read_only(tmp_path):
    with make_client(tmp_path) as client:
        _, headers, profile, url = setup(client)
        repo = client.app.state.repository
        before = repo.get_client_profile(profile["id"]).model_dump()
        assert submit(client, upload(begin(client))).status_code == 200
        view = client.get(url, headers=headers).json()
        assert view["state"] == "fresh" and not view["mapping_confirmed"]
        assert all(check["found"] for check in view["checks"])
        confirm = {
            "snapshot_id": view["snapshot"]["id"],
            "profile_fingerprint": view["profile_fingerprint"],
        }
        result = client.post(url + "/confirm", headers=headers, json=confirm)
        assert result.status_code == 200, result.text
        assert result.json()["mapping_confirmed"]
        assert repo.get_client_profile(profile["id"]).model_dump() == before
        with repo._connect() as connection:
            for table in (
                "invoices",
                "posting_attempts",
                "approval_plans",
                "connector_heartbeats",
            ):
                assert (
                    connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()[
                        "n"
                    ]
                    == 0
                )


def test_latest_ticket_wins_and_replay_cannot_overwrite(tmp_path):
    with make_client(tmp_path) as client:
        _, headers, _, url = setup(client)
        old, new = begin(client), begin(client)
        assert submit(client, upload(old)).status_code == 409
        assert submit(client, upload(new)).status_code == 200
        changed = upload(new)
        changed["masters"]["ledgers"] = []
        assert submit(client, changed).status_code == 409
        assert (
            len(
                client.get(url, headers=headers).json()["snapshot"]["masters"][
                    "ledgers"
                ]
            )
            == 2
        )


@pytest.mark.parametrize(
    "case", ["missing_kind", "duplicate", "wrong_company", "unknown_field"]
)
def test_bad_snapshot_preserves_last_good(tmp_path, case):
    with make_client(tmp_path) as client:
        _, headers, _, url = setup(client)
        assert submit(client, upload(begin(client))).status_code == 200
        before = client.get(url, headers=headers).json()["snapshot"]
        body = upload(begin(client))
        if case == "missing_kind":
            del body["masters"]["units"]
        if case == "duplicate":
            body["masters"]["units"] *= 2
        if case == "wrong_company":
            body["company"]["name"] = "OTHER"
        if case == "unknown_field":
            body["masters"]["units"][0]["balance"] = 99
        assert submit(client, body).status_code in (409, 422)
        assert client.get(url, headers=headers).json()["snapshot"] == before


def test_profile_change_invalidates_upload_and_confirmation_not_snapshot(tmp_path):
    with make_client(tmp_path) as client:
        org, headers, profile, url = setup(client)
        assert submit(client, upload(begin(client))).status_code == 200
        view = client.get(url, headers=headers).json()
        ticket = begin(client)
        settings = deepcopy(profile["settings"])
        settings["purchase_ledger"] = "MISSING"
        assert (
            client.patch(
                url.removesuffix("/tally-masters"),
                headers=headers,
                json={"settings": settings},
            ).status_code
            == 200
        )
        assert submit(client, upload(ticket)).status_code == 409
        assert (
            client.post(
                url + "/confirm",
                headers=headers,
                json={
                    "snapshot_id": view["snapshot"]["id"],
                    "profile_fingerprint": view["profile_fingerprint"],
                },
            ).status_code
            == 409
        )
        current = client.get(url, headers=headers).json()
        assert current["snapshot"] and not current["mapping_confirmed"]
        assert any(not check["found"] for check in current["checks"])
        settings["company_name"] = "OTHER"
        assert (
            client.patch(
                url.removesuffix("/tally-masters"),
                headers=headers,
                json={"settings": settings},
            ).status_code
            == 200
        )
        assert client.get(url, headers=headers).json()["snapshot"] is None


def test_stale_and_expired_sessions_fail_closed(tmp_path):
    with make_client(tmp_path) as client:
        _, headers, profile, url = setup(client)
        ticket = begin(client)
        repo = client.app.state.repository
        with repo._connect() as connection:
            connection.execute(
                "UPDATE tally_master_sync SET started_at = ? WHERE profile_id = ?",
                (
                    (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                    profile["id"],
                ),
            )
        assert submit(client, upload(ticket)).status_code == 409


def test_auth_roles_and_cross_workspace_isolation(tmp_path):
    with make_client(tmp_path) as client:
        org, headers, _, url = setup(client)
        assert (
            client.post(
                "/api/v1/connectors/tally/masters/begin",
                json={"workspace_id": "neel-prod"},
            ).status_code
            == 401
        )
        assert submit(client, upload(begin(client))).status_code == 200
        view = client.get(url, headers=headers).json()
        _invite_and_accept(client, org, headers, "viewer-masters@example.com", "viewer")
        viewer = client.post(
            "/api/v1/auth/login",
            json={
                "email": "viewer-masters@example.com",
                "password": "member-password-is-long",
            },
        ).json()
        viewer_headers = authorization(viewer)
        assert client.get(url, headers=viewer_headers).status_code == 200
        assert (
            client.post(
                url + "/confirm",
                headers=viewer_headers,
                json={
                    "snapshot_id": view["snapshot"]["id"],
                    "profile_fingerprint": view["profile_fingerprint"],
                },
            ).status_code
            == 403
        )
        assert client.get(
            url.replace(org, "another-org"), headers=headers
        ).status_code in (403, 404)
        assert "connector-secret-0123456789abcdef0123456789" not in client.get(url, headers=headers).text


def test_concurrent_submits_have_one_winner(tmp_path):
    with make_client(tmp_path) as client:
        setup(client)
        body = upload(begin(client))
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(lambda _: submit(client, body).status_code, range(2)))
        assert sorted(codes) == [200, 409]


def test_stale_snapshot_cannot_be_confirmed_and_resync_resets_confirmation(tmp_path):
    with make_client(tmp_path) as client:
        _, headers, profile, url = setup(client)
        assert submit(client, upload(begin(client))).status_code == 200
        view = client.get(url, headers=headers).json()
        body = {
            "snapshot_id": view["snapshot"]["id"],
            "profile_fingerprint": view["profile_fingerprint"],
        }
        assert (
            client.post(url + "/confirm", headers=headers, json=body).status_code == 200
        )
        repo = client.app.state.repository
        with repo._connect() as connection:
            row = connection.execute(
                "SELECT snapshot_json FROM tally_master_sync WHERE profile_id = ?",
                (profile["id"],),
            ).fetchone()
            snapshot = json.loads(row["snapshot_json"])
            snapshot["synced_at"] = (
                datetime.now(timezone.utc) - timedelta(days=2)
            ).isoformat()
            connection.execute(
                "UPDATE tally_master_sync SET snapshot_json = ? WHERE profile_id = ?",
                (json.dumps(snapshot), profile["id"]),
            )
        view = client.get(url, headers=headers).json()
        assert view["state"] == "stale" and not view["mapping_confirmed"]
        assert (
            client.post(url + "/confirm", headers=headers, json=body).status_code == 409
        )
        assert submit(client, upload(begin(client))).status_code == 200
        view = client.get(url, headers=headers).json()
        assert view["state"] == "fresh" and not view["mapping_confirmed"]


def test_inactive_inventory_settings_do_not_block_ledger_mappings(tmp_path):
    with make_client(tmp_path) as client:
        _, headers, profile, url = setup(client)
        settings = deepcopy(profile["settings"])
        settings.update(
            posting_mode="accounting_voucher",
            stock_item_name="NOT IN TALLY",
            stock_item_uom="MISSING",
        )
        assert (
            client.patch(
                url.removesuffix("/tally-masters"),
                headers=headers,
                json={"settings": settings},
            ).status_code
            == 200
        )
        assert submit(client, upload(begin(client))).status_code == 200
        view = client.get(url, headers=headers).json()
        assert all(check["found"] for check in view["checks"])
        assert not any(
            check["kind"] in ("stock_items", "units") for check in view["checks"]
        )


def test_sync_preserves_approved_frozen_plan_and_never_claims(tmp_path):
    from tests.test_approval_plans import prepared, preview, approve

    with make_client(tmp_path) as client:
        _, profile_id, invoice_id, headers = prepared(client)
        assert (
            approve(
                client,
                invoice_id,
                headers,
                preview(client, invoice_id, headers)["plan"],
            ).status_code
            == 200
        )
        repo = client.app.state.repository
        before = repo.get_approval_plan(invoice_id)
        assert submit(client, upload(begin(client))).status_code == 200
        assert repo.get_invoice(invoice_id).status == "approved"
        assert repo.get_approval_plan(invoice_id) == before
        with repo._connect() as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) AS n FROM posting_attempts"
                ).fetchone()["n"]
                == 0
            )
