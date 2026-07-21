"""Weekly digest tests: scheduling gate, content, duplicate guard, opt-out."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from siftentry_app.backend.digest_service import (
    DIGEST_SENT_EVENT,
    maybe_send_weekly_digests,
)

from .test_api import (
    authorization,
    bootstrap,
    import_sample_invoice,
    make_client,
    organization_id,
)

# Monday 04:00 UTC — past the default 03:00 send hour.
MONDAY_MORNING = datetime(2026, 7, 20, 4, 0, tzinfo=timezone.utc)
TUESDAY_MORNING = MONDAY_MORNING + timedelta(days=1)


def _enable_digest(client, tokens, org_id: str) -> None:
    headers = authorization(tokens)
    current = client.get(
        f"/api/v1/organizations/{org_id}/settings", headers=headers
    )
    assert current.status_code == 200
    settings = current.json()
    settings["notifications"]["digest"] = True
    saved = client.put(
        f"/api/v1/organizations/{org_id}/settings",
        json=settings,
        headers=headers,
    )
    assert saved.status_code == 200
    assert saved.json()["notifications"]["digest"] is True


def test_weekly_digest_sends_once_with_content(tmp_path: Path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        _enable_digest(client, tokens, org_id)
        import_sample_invoice(client, tokens, org_id)

        repo = client.app.state.repository
        email = client.app.state.email
        email.outbox.clear()

        # Wrong day: nothing happens.
        outcome = maybe_send_weekly_digests(repo, email, now=TUESDAY_MORNING)
        assert outcome["sent_orgs"] == 0
        assert email.outbox == []

        # Monday morning: one digest to the bootstrap owner.
        outcome = maybe_send_weekly_digests(repo, email, now=MONDAY_MORNING)
        assert outcome["sent_orgs"] == 1
        assert outcome["recipients"] == 1
        assert len(email.outbox) == 1
        delivered = email.outbox[0]
        assert "Your SiftEntry week" in delivered.subject
        assert "Invoices received: 1" in delivered.text_body
        assert "What needs you:" in delivered.text_body
        assert "Open SiftEntry" in delivered.html_body

        # The send is recorded for the duplicate guard.
        marker = repo.get_latest_audit_event(org_id, DIGEST_SENT_EVENT)
        assert marker is not None
        assert marker["details"]["recipients"] == 1
        assert marker["details"]["received"] == 1

        # Same morning, checked again 5 minutes later: no duplicate.
        outcome = maybe_send_weekly_digests(
            repo, email, now=MONDAY_MORNING + timedelta(minutes=5)
        )
        assert outcome["sent_orgs"] == 0
        assert len(email.outbox) == 1

        # Next Monday: it sends again.
        outcome = maybe_send_weekly_digests(
            repo, email, now=MONDAY_MORNING + timedelta(days=7)
        )
        assert outcome["sent_orgs"] == 1
        assert len(email.outbox) == 2


def test_weekly_digest_respects_toggle_and_quiet_weeks(tmp_path: Path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        repo = client.app.state.repository
        email = client.app.state.email
        email.outbox.clear()

        # Toggle off (the default): even with an invoice, nothing sends.
        import_sample_invoice(client, tokens, org_id)
        outcome = maybe_send_weekly_digests(repo, email, now=MONDAY_MORNING)
        assert outcome["sent_orgs"] == 0
        assert email.outbox == []
        assert repo.get_latest_audit_event(org_id, DIGEST_SENT_EVENT) is None


def test_weekly_digest_skips_empty_workspace(tmp_path: Path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        _enable_digest(client, tokens, org_id)
        repo = client.app.state.repository
        email = client.app.state.email
        email.outbox.clear()

        # Toggle on but nothing at all to report: stay silent, leave no
        # marker (so activity later the same day still gets a digest).
        outcome = maybe_send_weekly_digests(repo, email, now=MONDAY_MORNING)
        assert outcome["sent_orgs"] == 0
        assert email.outbox == []
        assert repo.get_latest_audit_event(org_id, DIGEST_SENT_EVENT) is None
