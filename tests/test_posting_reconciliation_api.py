from concurrent.futures import ThreadPoolExecutor
from xml.etree import ElementTree as ET

import pytest
from tests.test_api import make_client, CONNECTOR_HEADERS
from tests.test_approval_plans import prepared, preview, approve
from tests.test_tally_master_api import begin, upload, submit


def call(client, path, **values):
    return client.post(
        "/api/v1/connectors/tally/jobs/" + path,
        headers=CONNECTOR_HEADERS,
        json={"workspace_id": "neel-prod", **values},
    )


def ready(client, permit=True):
    org, profile, invoice, headers = prepared(client)
    plan = preview(client, invoice, headers)["plan"]
    assert approve(client, invoice, headers, plan).status_code == 200
    assert submit(client, upload(begin(client))).status_code == 200
    job = call(client, "claim", reconciliation_protocol=1).json()["jobs"][0]
    if permit:
        assert call(client, "begin", posting_id=job["posting_id"]).status_code == 200
    return job, headers


def proof(job):
    node = ET.fromstring(job["xml"]).find(".//VOUCHER")
    for tag, value in (("ISCANCELLED", "No"), ("ISOPTIONAL", "No"), ("MASTERID", "42")):
        if node.find(tag) is None:
            ET.SubElement(node, tag).text = value
        else:
            node.find(tag).text = value
    return ET.tostring(node, encoding="unicode")


def evidence(client, job, **overrides):
    values = {
        "posting_id": job["posting_id"],
        "company": {"name": "NEEL ENTERPRISE", "guid": "company-guid"},
        "voucher_xml": proof(job),
    }
    return call(client, "reconcile", **{**values, **overrides})


def test_found_exact_entry_finishes_atomically_and_replay_is_idempotent(tmp_path):
    with make_client(tmp_path) as client:
        job, _ = ready(client)
        repo = client.app.state.repository
        result = evidence(client, job)
        assert result.status_code == 200, result.text
        assert result.json()["won"]
        assert not evidence(client, job).json()["won"]
        assert repo.get_invoice(job["invoice_id"]).status == "posted"
        posting = repo.get_posting(job["posting_id"])
        assert posting.raw["reconciliation"]["state"] == "matched"
        assert posting.raw["execution"]["company"]["guid"] == "company-guid"
        with repo._connect() as conn:
            assert (
                conn.execute(
                    "SELECT COUNT(*) AS n FROM audit_events WHERE invoice_id = ? AND event_type = 'posting.reconciled'",
                    (job["invoice_id"],),
                ).fetchone()["n"]
                == 1
            )
        assert call(client, "recovery").json()["jobs"] == []
        assert call(client, "recovery", posting_ids=[job["posting_id"]]).json()["jobs"][
            0
        ]["reconciled"]


def test_two_execution_requests_have_exactly_one_winner(tmp_path):
    with make_client(tmp_path) as client:
        job, _ = ready(client, permit=False)
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(
                pool.map(
                    lambda _: call(
                        client, "begin", posting_id=job["posting_id"]
                    ).status_code,
                    range(2),
                )
            )
        assert sorted(codes) == [200, 409]


@pytest.mark.parametrize(
    "case", ["wrong_company", "wrong_amount", "empty", "legacy", "no_permit"]
)
def test_inconclusive_evidence_keeps_invoice_reserved(tmp_path, case):
    with make_client(tmp_path) as client:
        job, _ = ready(client, permit=case != "no_permit")
        args = {}
        if case == "wrong_company":
            args["company"] = {"name": "NEEL ENTERPRISE", "guid": "other-company"}
        if case == "wrong_amount":
            node = ET.fromstring(proof(job))
            node.find(".//AMOUNT").text = "999999"
            args["voucher_xml"] = ET.tostring(node, encoding="unicode")
        if case == "empty":
            args.update(voucher_xml="", message="No unique match; do not repost.")
        if case == "legacy":
            args["voucher_xml"] = proof(job).replace(
                job["posting_plan"]["posting_reference"], "legacy-id"
            )
        result = evidence(client, job, **args)
        assert result.status_code == 409 or not result.json()["success"]
        assert (
            client.app.state.repository.get_invoice(job["invoice_id"]).status
            == "posting"
        )
        response = call(client, "claim", reconciliation_protocol=1).json()
        assert response["jobs"] == [] and response["recovery_required"]


def test_recovery_is_authenticated_and_profile_scoped(tmp_path):
    with make_client(tmp_path) as client:
        job, _ = ready(client)
        for path in ("recovery", "begin", "reconcile"):
            result = client.post(
                "/api/v1/connectors/tally/jobs/" + path,
                json={
                    "workspace_id": "neel-prod",
                    **({"posting_id": job["posting_id"]} if path != "recovery" else {}),
                },
            )
            assert result.status_code == 401
        assert (
            call(client, "recovery", posting_ids=["other-tenant-posting"]).json()[
                "jobs"
            ][0]["posting_id"]
            == job["posting_id"]
        )
        assert (
            call(client, "begin", posting_id="other-tenant-posting").status_code == 409
        )


def test_old_connector_cannot_claim_new_plans_and_unpermitted_results_rejected(
    tmp_path,
):
    with make_client(tmp_path) as client:
        _, _, invoice, headers = prepared(client)
        assert (
            approve(
                client, invoice, headers, preview(client, invoice, headers)["plan"]
            ).status_code
            == 200
        )
        assert call(client, "claim").status_code == 409
        job = call(client, "claim", reconciliation_protocol=1).json()["jobs"][0]
        for uncertain in (False, True):
            result = call(
                client,
                "results",
                results=[
                    {
                        "posting_id": job["posting_id"],
                        "invoice_id": invoice,
                        "success": False,
                        "outcome_uncertain": uncertain,
                    }
                ],
            ).json()
            assert result["rejected"] == 1
        assert client.app.state.repository.get_invoice(invoice).status == "posting"


def test_concurrent_reconciliation_and_failure_do_not_overwrite_winner(tmp_path):
    with make_client(tmp_path) as client:
        job, _ = ready(client)

        def run(kind):
            if kind == "reconcile":
                return evidence(client, job)
            return call(
                client,
                "results",
                results=[
                    {
                        "posting_id": job["posting_id"],
                        "invoice_id": job["invoice_id"],
                        "success": False,
                        "message": "Definite rejection",
                    }
                ],
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(run, ["reconcile", "failure"]))
        repo = client.app.state.repository
        posting = repo.get_posting(job["posting_id"])
        assert repo.get_invoice(job["invoice_id"]).status == (
            "posted" if posting.success else "failed"
        )
        assert posting.raw.get("late_result_conflicts")


def test_company_identity_is_frozen_and_changed_snapshot_requires_reapproval(tmp_path):
    with make_client(tmp_path) as client:
        _, profile, invoice, headers = prepared(client)
        original = preview(client, invoice, headers)["plan"]
        assert original["company_guid"] == "company-guid"
        assert approve(client, invoice, headers, original).status_code == 200
        changed = upload(begin(client))
        changed["company"]["guid"] = "new-company-guid"
        assert submit(client, changed).status_code == 200
        assert call(client, "claim", reconciliation_protocol=1).json()["jobs"] == []
        current = preview(client, invoice, headers)
        assert current["requires_reapproval"]
        assert current["plan"]["company_guid"] == "new-company-guid"
        assert current["plan"]["posting_reference"] == original["posting_reference"]
        assert (
            client.app.state.repository.get_approval_plan(invoice)["company_guid"]
            == "company-guid"
        )


def test_missing_company_snapshot_blocks_approval_not_just_posting(tmp_path):
    with make_client(tmp_path) as client:
        _, profile, invoice, headers = prepared(client)
        with client.app.state.repository._connect() as connection:
            connection.execute(
                "DELETE FROM tally_master_sync WHERE profile_id = ?", (profile,)
            )
        plan = preview(client, invoice, headers)["plan"]
        assert any("identity" in message for message in plan["blocking_issues"])
        assert approve(client, invoice, headers, plan).status_code == 409


def test_frozen_company_used_for_recovery_after_profile_edit(tmp_path):
    from siftentry_app.backend.models import ClientProfilePatch

    with make_client(tmp_path) as client:
        job, _ = ready(client)
        repo = client.app.state.repository
        profile = repo.get_client_profile(job["client_profile_id"])
        settings = profile.settings.model_copy(deep=True)
        settings.company_name = "NEW COMPANY"
        repo.update_client_profile(profile.id, ClientProfilePatch(settings=settings))
        assert evidence(client, job).json()["state"] == "matched"
        assert (
            repo.get_posting(job["posting_id"]).raw["execution"]["company"]["name"]
            == "NEEL ENTERPRISE"
        )


def test_repeated_inconclusive_checks_do_not_flood_history(tmp_path):
    with make_client(tmp_path) as client:
        job, _ = ready(client)
        for _ in range(3):
            evidence(client, job, voucher_xml="", message="No unique match")
        with client.app.state.repository._connect() as conn:
            assert (
                conn.execute(
                    "SELECT COUNT(*) AS n FROM audit_events WHERE invoice_id = ? AND event_type = 'posting.reconciliation_held'",
                    (job["invoice_id"],),
                ).fetchone()["n"]
                == 1
            )
