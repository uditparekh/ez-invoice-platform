"""SiftEntry background worker.

Runs slow work outside HTTP requests: batch posting today, AI extraction
and the `extract` merge policy next. Start alongside the API:

    make worker            # or: python -m siftentry_app.backend.worker

Multiple workers are safe: jobs are claimed atomically (PostgreSQL uses
FOR UPDATE SKIP LOCKED; SQLite uses an atomic UPDATE ... RETURNING).
The worker builds the same app object as the API, so adapters, storage,
and repository wiring are identical by construction.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict

from .main import _execute_posting, create_app
from .models import AuthenticatedUser, PostingTarget
from .settings import ApiSettings

logger = logging.getLogger("siftentry.worker")

POLL_SECONDS = float(os.environ.get("SIFTENTRY_WORKER_POLL_SECONDS", "2.0"))


def _worker_user(actor_id: str) -> AuthenticatedUser:
    now = datetime.now(timezone.utc)
    return AuthenticatedUser(
        id=actor_id or "worker",
        email="worker@siftentry.local",
        full_name="SiftEntry Worker",
        is_active=True,
        created_at=now,
        updated_at=now,
        last_login_at=None,
        memberships=[],
    )


def _request_shim(app) -> SimpleNamespace:
    """_execute_posting only reads request.app.state — give it exactly that."""
    return SimpleNamespace(app=app)


def execute_job(app, job) -> Dict[str, Any]:
    """Dispatch one claimed job. Returns the result payload to store."""
    repo = app.state.repository
    if job.kind == "batch_post_ready":
        payload = job.payload or {}
        wanted_status = str(payload.get("status") or "approved")
        target = (
            PostingTarget(payload["target"]) if payload.get("target") else None
        )
        candidates = [
            invoice
            for invoice in repo.list_invoices(
                organization_id=job.organization_id, limit=100_000, offset=0
            )
            if (
                invoice.status.value
                if hasattr(invoice.status, "value")
                else str(invoice.status)
            )
            == wanted_status
        ]
        request = _request_shim(app)
        user = _worker_user(job.actor_id)
        succeeded = 0
        failed = 0
        skipped = []
        for invoice in candidates:
            try:
                result = _execute_posting(
                    request,
                    user,
                    invoice,
                    target=target,
                    client_profile_id=payload.get("client_profile_id"),
                    dry_run=bool(payload.get("dry_run", False)),
                )
                succeeded += 1 if result.success else 0
                failed += 0 if result.success else 1
            except Exception as exc:  # HTTPException detail or config error
                skipped.append(
                    {"invoice_id": invoice.id, "reason": str(getattr(exc, "detail", exc))}
                )
        return {
            "attempted": len(candidates),
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
        }
    raise ValueError(f"Unknown job kind: {job.kind}")


def run_once(app) -> bool:
    """Claim and run at most one job. Returns True if a job was processed."""
    repo = app.state.repository
    job = repo.claim_next_job()
    if not job:
        return False
    logger.info("job %s (%s) claimed", job.id, job.kind)
    try:
        result = execute_job(app, job)
        repo.finish_job(job.id, result=result)
        logger.info("job %s done: %s", job.id, result)
    except Exception as exc:
        repo.finish_job(job.id, error=str(exc))
        logger.exception("job %s failed", job.id)
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    settings = ApiSettings.from_environment()
    app = create_app(settings)
    logger.info(
        "worker started (db=%s, poll=%ss)",
        "postgres" if settings.database_url.startswith("postgres") else "sqlite",
        POLL_SECONDS,
    )
    while True:
        if not run_once(app):
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
