# SiftEntry Cumulative Package Changelog

Tracks every file changed per delivered package, against the repo state each
package was built on. Started at pkg32; earlier packages are recorded in
CHANGELOG.md and their README-INTEGRATION files.

## pkg34 r2 — posting safety (Batch A), built against main @ ee310f2

Revision 2 after the 10 Sep shipping verification found three failures in r1:
(1) results persisted per batch, not per job; (2) acknowledgements skipped
when Tally was closed; (3) terminal results decided by a read-then-write.
All three fixed and covered by regression tests. Also: website download link
→ 0.4.0, desktop passes config_path to the runtime, unreadable outbox fails
visibly and blocks new claims.

Changes vs r1:
- tally_connector_runtime.py — drain outbox BEFORE the Tally check;
  append_outbox after EACH job; OutboxUnreadable raised on corrupt file and
  surfaced as a blocking status
- repository.py — _complete_posting_unchecked is a conditional UPDATE
  (WHERE status='started') returning (posting, won); complete_posting_atomic
  decides by rowcount; conflicts recorded for losers
- main.py — results handler uses complete_posting_atomic and moves the
  invoice only when won
- tally_connector_desktop.py — current_config passes config_path
- accounting-system-page.tsx — download link 0.4.0
- tests: +3 outbox regressions, +1 concurrent conflicting-results test

Backend tests: 89 → 100. Web: typecheck/lint/build clean.


Backend (3 changed):
- siftentry_app/backend/repository.py — partial unique active-claim index,
  approved-only ready query, claim_invoice_for_posting / release_invoice_claim
  (atomic CAS), idempotent complete_posting wrapper + record_posting_conflict
- siftentry_app/backend/main.py — PostingStatus import, CAS in claim handler,
  results only move invoice when the posting was open, _redact_profile_secrets
  on all profile reads, _preserve_connector_token on update,
  connector-credentials endpoint (MANAGE_ROLES)
- siftentry_app/backend/models.py — (unchanged this package)

Connector (3 changed):
- siftentry_app/tally_connector_runtime.py — 0.4.0, config_path on
  ConnectorConfig, durable results outbox (read/write/append/drain), poll_once
  drains first and persists before ack
- siftentry_app/tally_connector_desktop.py — poll_lock, Poll once refused while
  running, --autostart flag, autostart on launch when settings complete
- packaging/windows/tally-connector/SiftEntryTallyConnector.iss — 0.4.0,
  --autostart on the sign-in Run entry
- packaging/windows/tally-connector/CLIENT_INSTALL_GUIDE.md — 0.4.0 filename
- .github/workflows/build-tally-connector.yml — action version bumps

Tests (2: 1 changed, 1 new):
- tests/test_api.py — 5 acceptance tests (viewer secrets, token preserved on
  save, approved-only, overlapping claims, late failure)
- tests/test_connector_outbox.py — NEW, restart-after-success retry + dedupe

Web (5: 4 changed, 1 new):
- apps/web/src/components/auth-provider.tsx — navigation effect keeps session
- apps/web/src/components/client-profiles-panel.tsx — token field write-only copy
- apps/web/src/components/accounting/accounting-system-page.tsx —
  ConnectorCredentialsReveal on Integrations
- apps/web/src/app/(product)/app/history/page.tsx — audit-grade claims removed
- apps/web/src/app/api/organizations/[organizationId]/client-profiles/[profileId]/connector-credentials/route.ts — NEW

Docs (3 changed): CHANGELOG.md, README-INTEGRATION.md, SIFTENTRY_CHANGELOG.md

Backend tests: 89 → 96. Web: typecheck/lint/build clean, 41 pages.
A NEW INSTALLER BUILD (0.4.0) IS REQUIRED after pushing.

## pkg33-c — hotfix, built on pkg33-b

Creating a workspace logged the user out.

Web (2 changed):
- apps/web/src/components/create-workspace-dialog.tsx — refresh session
  before switching workspace
- apps/web/src/components/auth-provider.tsx — refresh() keeps the session
  on transient failures; only 401/403 clears it

Docs (3 changed): CHANGELOG.md, README-INTEGRATION.md, SIFTENTRY_CHANGELOG.md

## pkg33-b — built against main @ 3517528

Create-workspace button and dialog; the missing pkg33 PATCH proxy route is
re-included because it was absent from the pkg33 push.

Web (3 changed, 2 new):
- apps/web/src/app/api/organizations/route.ts — POST proxy added
- apps/web/src/components/create-workspace-dialog.tsx — NEW
- apps/web/src/components/app-shell.tsx — header "+" button, dialog mounted
- apps/web/src/app/(product)/app/settings/page.tsx — New workspace card
  under Organization
- apps/web/src/app/api/organizations/[organizationId]/members/[userId]/route.ts
  — from pkg33; re-shipped (missing upstream)

Docs (3 changed):
- CHANGELOG.md, README-INTEGRATION.md, SIFTENTRY_CHANGELOG.md

Backend: unchanged (89 tests). Web: typecheck/lint/build clean, 41 pages.

## pkg33 — built against main @ 4c6bd2d

Consolidation & trust: collapsible profile library, ledger section rebuilt
into concept groups, AI readiness as a sentence with aligned required flags,
mappings canonical in Rules & mapping, member role changes, wizard field
wiring fix, viewport fix, orphan route removed.

Backend (2 changed):
- siftentry_app/backend/models.py — MemberRoleUpdate
- siftentry_app/backend/main.py — PATCH members/{user_id} endpoint with
  owner-promotion and last-owner guards

Tests (1 changed):
- tests/test_api.py — 3 role-change tests

Web (5 changed, 1 new, 1 deleted):
- apps/web/src/components/client-profiles-panel.tsx — library rail,
  FieldGroup + hint/optional on TextField, ledger section rebuilt, mapping
  row → count + link, readiness merged into training panel, sentence status,
  inline status on instruction textareas, dead mapping helpers removed
- apps/web/src/components/client-profiles/profile-wizard.tsx — expectations
  field writes posting_expectations
- apps/web/src/components/settings/team-management-panel.tsx — role select
  on member rows
- apps/web/src/app/layout.tsx — viewport object corrected, Viewport type
- apps/web/src/app/api/organizations/[organizationId]/members/[userId]/route.ts
  — NEW, PATCH proxy
- apps/web/src/app/(product)/app/gl-mapping/page.tsx — DELETED (orphan demo)

Docs (3 changed):
- CHANGELOG.md, README-INTEGRATION.md, SIFTENTRY_CHANGELOG.md

Backend tests: 86 → 89. Web: typecheck/lint/build clean, 41 static pages
(was 42 — the orphan route).

## pkg32 — built against main @ e76a514

Voucher-with-stock-allocation posting mode, connector double-posting guard,
PWA build refresh, golden XML tests for all three Tally posting modes.

Backend (4 changed):
- siftentry_app/backend/models.py — VOUCHER_WITH_INVENTORY enum member
- siftentry_app/tally_integration.py — posting-mode alias sets and helpers,
  _build_voucher_inventory_entries, third envelope branch in build_tally_xml,
  preflight covers both inventory-backed modes
- siftentry_app/backend/adapters.py — 3-way posting-mode label map replaces
  the binary item_invoice/accounting-voucher ternary
- siftentry_app/backend/main.py — INVENTORY_POSTING_MODES constant,
  ProfilePostingMode import, preflight widened, _guard_single_connector_profile
  wired into profile create and update

Tests (2 changed):
- tests/test_tally_integration.py — 7 golden/preflight tests for the three
  posting modes (build_tally_xml previously untested)
- tests/test_api.py — 4 connector-guard tests

Web (6: 4 changed, 2 new):
- apps/web/src/lib/types.ts — voucher_with_inventory in ProfilePostingMode
- apps/web/src/components/client-profiles/profile-wizard.tsx — three
  posting-mode cards, label map in review step
- apps/web/src/components/client-profiles-panel.tsx — dropdown option, stock
  readiness checklist covers both inventory-backed modes
- apps/web/src/app/layout.tsx — BuildRefresh mounted
- apps/web/src/app/api/system/build/route.ts — NEW, no-store build-id endpoint
- apps/web/src/components/build-refresh.tsx — NEW, deployment poller

Docs (3: 2 changed, 1 new):
- CHANGELOG.md — pkg32 entries
- README-INTEGRATION.md — pkg32 delivery instructions
- SIFTENTRY_CHANGELOG.md — NEW, this file

Backend tests: 75 → 86. Web: typecheck/lint/build clean, 42/42 routes,
/api/system/build added.
