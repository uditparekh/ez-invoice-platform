# SiftEntry — Weekly Email Digest, pkg19 (July 20, 2026)

## APPLY ORDER — read first
IMPORTANT: apply pkg18 (Tally connector productization) FIRST, commit
and push it, THEN apply this package. Two files in this zip
(repository.py and CHANGELOG.md) contain pkg18's changes plus pkg19's —
applying pkg19 without pkg18 would silently include half of pkg18
without its other files, and the diffs would not match either README.

1. Confirm your latest commit is pkg18
   ("Tally connector productization: heartbeat, live status card,
   client kit") and it is pushed.
2. Unzip this package over the repo root, replacing files when asked.
3. Review the changed-files list in GitHub Desktop against the counts
   below. STOP IF YOU SEE RED BLOCKS in any file NOT listed here.

## What this adds
The Settings → Notifications "Weekly digest" toggle has existed since
the settings page shipped — it saved fine and did nothing. This makes
it real. Every Monday at 03:00 UTC (08:30 AM IST, chosen for the Tally
pilot; overridable), the Railway worker emails each active member of
every workspace that has the toggle on:

- Invoices received in the last 7 days
- Posted count and total value (per currency)
- Failed postings to retry
- "What needs you": needs-review / awaiting-approval / ready-to-post
  counts right now
- Supplier formats still in training + newly detected formats (Phase B)
- A warning if a configured Tally connector is offline (pkg18's
  heartbeat data, first reuse)

Safety: workspaces with the toggle off are never touched (today's
behavior). Completely quiet workspaces are skipped — no empty emails.
A digest.sent audit event per organization prevents duplicates across
worker restarts. Recipients are all active members (org-level toggle,
matching what the UI offers; per-user opt-out is a later pass).

## Files (7 changed/added)

Backend (4):
- siftentry_app/backend/digest_service.py — NEW: gathers the weekly
  numbers, renders the text + HTML email, scheduling gate + duplicate
  guard (maybe_send_weekly_digests)
- siftentry_app/backend/email_service.py — new send_weekly_digest using
  the same branded template as invites/resets
- siftentry_app/backend/worker.py — digest check every 5 minutes
  alongside job polling (SIFTENTRY_DIGEST_CHECK_SECONDS)
- siftentry_app/backend/repository.py — list_recent_postings,
  record_audit_event, get_latest_audit_event
  (NOTE: this file also carries pkg18's heartbeat methods — apply order
  above)

Tests (1):
- tests/test_digest.py — NEW: wrong-day gate, Monday send with correct
  content and recipient, duplicate guard within the same Monday, resend
  next Monday, toggle-off skip, quiet-workspace skip

Docs (2):
- CHANGELOG.md — pkg19 entry added above pkg18's (both present)
- README-INTEGRATION.md — this file

## Diff expectations
- All green additions. Small red blocks ONLY in:
  - worker.py: the _poll_forever loop gains the digest check (its old
    3-line body is replaced by ~12 lines)
- If repository.py shows red beyond nothing (it should be green-only on
  top of pkg18): STOP.

## Environment (all optional, defaults shown)
- SIFTENTRY_DIGEST_DAY=0            (0=Monday … 6=Sunday)
- SIFTENTRY_DIGEST_HOUR_UTC=3       (03:00 UTC = 08:30 IST)
- SIFTENTRY_DIGEST_CHECK_SECONDS=300
Nothing to add on Railway — the worker service already has the email
env vars (EZ_EMAIL_PROVIDER=resend, EZ_RESEND_API_KEY, EZ_EMAIL_FROM,
EZ_APP_BASE_URL). Confirm EZ_APP_BASE_URL=https://app.siftentry.com on
the WORKER service too, since the digest's button links there.

## Commit message
Weekly email digest: worker-sent Monday summary honoring the settings toggle

## Verify steps
1. `python3 -m pytest -q` → 65 passed (was 62 after pkg18).
2. Frontend untouched — no pnpm run needed; route count unchanged.
3. Push; Railway redeploys API + worker.
4. In app.siftentry.com → Settings → Notifications, turn ON "Weekly
   digest" for your workspace.
5. To see one immediately instead of waiting for Monday: on the Railway
   worker service, temporarily set SIFTENTRY_DIGEST_DAY to today's
   weekday number (Mon=0 … Sun=6) and SIFTENTRY_DIGEST_HOUR_UTC=0,
   redeploy the worker, and within ~5 minutes every member gets the
   email. Remove both vars afterwards to return to Mondays.
6. Check the email: counts match the dashboard, the connector-offline
   line appears only if the Tally connector is stopped, and the button
   opens app.siftentry.com.

## Notes
- Duplicate guard is 3 days: a digest sent Monday cannot resend before
  Thursday even if env vars are fiddled — delete-and-resend requires a
  new week or a fresh workspace.
- The digest reuses pkg18's heartbeat table; if pkg18 is not deployed
  the connector-offline line simply never appears (table exists but
  stays empty until a v0.3.0 connector checks in).
