"""Async job queue + worker tests (Step 12). Runs on both engines."""

from pathlib import Path

from siftentry_app.backend import worker as worker_module

from .test_api import (
    authorization,
    bootstrap,
    import_sample_invoice,
    make_client,
    organization_id,
)


def test_enqueue_and_worker_executes_batch_posting(tmp_path: Path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        headers = authorization(tokens)

        # Two approved invoices, one not ready.
        for name in ("job-1.pdf", "job-2.pdf"):
            invoice = import_sample_invoice(client, tokens, org_id, name)
            client.post(f"/api/v1/invoices/{invoice['id']}/validate", headers=headers)
            client.post(f"/api/v1/invoices/{invoice['id']}/approve", headers=headers)
        import_sample_invoice(client, tokens, org_id, "job-not-ready.pdf")

        # Enqueue returns 202 + a pollable job.
        response = client.post(
            f"/api/v1/organizations/{org_id}/jobs/post-ready",
            json={"dry_run": True},
            headers=headers,
        )
        assert response.status_code == 202
        enqueued = response.json()
        job_id = enqueued["job"]["id"]
        assert enqueued["job"]["status"] == "queued"
        assert enqueued["poll_url"].endswith(job_id)

        # Job is visible in the org list, still queued (no worker yet).
        jobs = client.get(
            f"/api/v1/organizations/{org_id}/jobs", headers=headers
        ).json()
        assert any(job["id"] == job_id for job in jobs)

        # Run the worker loop once against the SAME app wiring.
        assert worker_module.run_once(client.app) is True
        assert worker_module.run_once(client.app) is False  # queue drained

        # Poll: done, with per-invoice accounting.
        finished = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
        assert finished["status"] == "done", finished
        assert finished["result"]["attempted"] == 2
        assert (
            finished["result"]["succeeded"]
            + finished["result"]["failed"]
            + len(finished["result"]["skipped"])
            >= 2
        )

        # Unauthenticated job polling is rejected.
        assert client.get(f"/api/v1/jobs/{job_id}").status_code == 401


def test_claim_is_atomic_and_single_delivery(tmp_path: Path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        repo = client.app.state.repository

        first = repo.enqueue_job(org_id, "batch_post_ready", {"dry_run": True})
        second = repo.enqueue_job(org_id, "batch_post_ready", {"dry_run": True})

        claim_a = repo.claim_next_job()
        claim_b = repo.claim_next_job()
        claim_c = repo.claim_next_job()
        assert claim_a and claim_b and claim_c is None
        assert {claim_a.id, claim_b.id} == {first.id, second.id}  # each once, oldest first
        assert claim_a.status == "running" and claim_a.attempts == 1

        repo.finish_job(claim_a.id, result={"ok": True})
        repo.finish_job(claim_b.id, error="boom")
        assert repo.get_job(claim_a.id).status == "done"
        failed = repo.get_job(claim_b.id)
        assert failed.status == "failed" and failed.error == "boom"
