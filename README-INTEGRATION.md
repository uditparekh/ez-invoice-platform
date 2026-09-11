# pkg34 r2 — Posting safety (Batch A from the 10 Sep QA review)

## Shipping addendum

The integrated release includes additional hardening and regression tests beyond
the original 17-file archive. See [the release/runbook](docs/PKG34-RELEASE.md)
for the authoritative implementation, safe branch-first installer publication,
and remaining real-Windows/Tally checks. Local backend verification: 113 tests.
The original archive notes below are retained for traceability; their two-push
main procedure is superseded by the release-branch process (no download outage).

Built against: main @ ee310f2 (confirmed by your shipping verification as
the current main; my local snapshot matches pkg33-c which is that commit).
This is REVISION 2: r1 failed three shipping gates (per-batch persistence,
ack skipped when Tally closed, non-atomic terminal results). All three are
fixed here with regression tests. Do not apply r1.

## Files in this zip: 17 total (15 changed, 2 new)

Backend (2 changed):
1.  siftentry_app/backend/repository.py
2.  siftentry_app/backend/main.py

Connector + installer (5 changed):
3.  siftentry_app/tally_connector_runtime.py
4.  siftentry_app/tally_connector_desktop.py
5.  packaging/windows/tally-connector/SiftEntryTallyConnector.iss
6.  packaging/windows/tally-connector/CLIENT_INSTALL_GUIDE.md
7.  .github/workflows/build-tally-connector.yml

Tests (1 changed, 1 new):
8.  tests/test_api.py
9.  tests/test_connector_outbox.py                              (NEW)

Web (4 changed, 1 new):
10. apps/web/src/components/auth-provider.tsx
11. apps/web/src/components/client-profiles-panel.tsx
12. apps/web/src/components/accounting/accounting-system-page.tsx
13. apps/web/src/app/(product)/app/history/page.tsx
14. apps/web/src/app/api/organizations/[organizationId]/client-profiles/[profileId]/connector-credentials/route.ts
    (NEW — two bracketed folders: [profileId] then connector-credentials.
    Bracketed folders have been skipped by Finder before — verify on GitHub
    after pushing that this file is present.)

Docs (3 changed):
15. CHANGELOG.md
16. SIFTENTRY_CHANGELOG.md
17. README-INTEGRATION.md (this file)

## What this package delivers — the QA acceptance criteria

| QA finding | Fix | Proof |
| --- | --- | --- |
| Viewer receives connector token | Token redacted on every profile read; write-only; owner/admin reveal endpoint | test_viewer_never_receives_connector_token |
| Saving would blank the token | Update preserves stored token when incoming is empty | test_saving_a_redacted_profile_keeps_the_stored_token |
| Validated invoices post without approval | Claim query is approved-only | test_only_approved_invoices_are_offered_to_the_connector |
| Two overlapping polls claim one invoice | Atomic conditional UPDATE + partial unique index | test_overlapping_claims_yield_exactly_one_owner (2 synchronized threads) |
| Late failure overwrites success | Terminal results idempotent; conflicts recorded, never applied | test_late_failure_cannot_overwrite_a_successful_posting |
| Tally success loses its ack | Durable outbox; each result on disk right after its Tally post; drained every poll BEFORE the Tally check; no new claims while pending | test_tally_success_with_failed_ack_is_retried_without_reposting; test_interrupted_batch_keeps_earlier_results_on_disk; test_pending_ack_is_sent_even_when_tally_is_closed |
| Corrupt outbox treated as empty | OutboxUnreadable → blocking status, evidence preserved | test_unreadable_outbox_blocks_new_claims_visibly |
| Simultaneous success+failure results | Conditional UPDATE WHERE status='started'; only the winner moves the invoice | test_concurrent_conflicting_results_cannot_overwrite_success (2 synchronized threads) |
| Autostart does not start | --autostart on sign-in entry; app starts polling if settings complete | source; verify on Windows (step 6 below) |
| Poll once races the loop | Shared lock; Poll once refused while running | source; verify on Windows |
| Navigation effect signs out on blips | Keeps session; only 401/403 signs out | source |
| "Audit-grade" claim | Removed; honest copy | visible |

Connector version is now 0.4.0. Old 0.3.0 installs keep working against the
new backend (the API is unchanged) but lack the outbox and autostart — every
client should get 0.4.0.

## Diff expectations in GitHub Desktop

- repository.py: green index block after posting_attempts CREATE TABLE; a
  small red/green in list_connector_ready_invoices (VALIDATED → APPROVED);
  green claim_invoice_for_posting + release_invoice_claim before set_status;
  green complete_posting wrapper + record_posting_conflict, and the original
  complete_posting renamed to _complete_posting_unchecked (one red/green
  line). Nothing else. If you see red inside invoice or profile CRUD: STOP.
- main.py: one green import line (PostingStatus); green helper block
  (_redact_profile_secrets, _preserve_connector_token) above
  _connector_is_enabled; green connector-credentials endpoint before the
  profile PATCH; small red/green wrapping each profile-endpoint return in
  _redact_profile_secrets; green _preserve_connector_token call in
  update_client_profile; red/green in the claim loop (CAS + try/except);
  red/green in the results loop (was_open guard). If you see red in Tally XML
  building, auth, or invitations: STOP.
- tally_connector_runtime.py: version 0.3.0 → 0.4.0; config_path field;
  green outbox block after default_config_path; red/green in poll_once
  (drain first; persist before submit; awaiting_ack).
- tally_connector_desktop.py: __init__ signature gains autostart; green
  poll_lock + autostart block; red/green in poll_once_now/_poll_once_worker
  and _poll_loop; green --autostart arg and constructor call.
- .iss: version 0.4.0, "--minimized --autostart".
- workflow: three "uses:" version bumps only.
- test files, web files, docs: green (plus one red import line in history).

## Commit message

Posting safety: write-only connector token, atomic approved-only claims, idempotent results, durable ack outbox, real autostart (connector 0.4.0)

## Verify steps

1. Backend: `python3 -m pytest -q` → 100 passed (was 89).
2. Web, from apps/web: `pnpm typecheck && pnpm lint && pnpm build` → clean.
3. Push, confirm on GitHub that file 14 exists, let Railway + Vercel deploy.
4. REBUILD AND PUBLISH THE INSTALLER (two pushes — read this fully):
   a. After push 1 (this package) deploys, run Actions → Build Tally
      connector installer → Run workflow (main). Download the artifact:
      SiftEntry-Tally-Connector-Setup-0.4.0.exe.
   b. Copy that .exe into apps/web/public/downloads/ next to the 0.3.0 one
      (the website's Download button serves from that folder — this
      package changed the link to 0.4.0, so until the file is there the
      button returns 404). Delete the 0.3.0 file. Commit + push (push 2):
      "Publish connector installer 0.4.0".
   c. Send clients the 0.4.0 file, never 0.3.0.
5. In the app: Integrations → the Tally profile card has "Reveal connector
   token" (owners/admins). Client profiles → connection settings → token
   field shows "Saved — leave blank to keep it"; Save profile; the
   connector still authenticates.
6. On a Windows PC (your Neel visit, BEFORE any live post): install 0.4.0,
   fill settings, Start, then RESTART THE PC. The connector should come up
   and show Running on its own. Then click "Poll once" while Running → the
   log says background polling covers it.
7. Optional but recommended on Windows: with Tally open, approve one TEST
   invoice, pull the network cable right after the Tally voucher appears,
   watch the connector say "not yet confirmed — retrying"; plug back in;
   it confirms without a second voucher in Tally.

## Guide update

The client guide (v1.1) still says "after every restart, click Start
connector" and "Poll once" warnings. Once you have verified step 6 on a real
PC, tell me and I'll issue guide v1.2 removing those notes and stating
0.4.0. Do not send v1.2 before that verification.
