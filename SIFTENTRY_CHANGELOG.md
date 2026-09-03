# SiftEntry Cumulative Package Changelog

Tracks every file changed per delivered package, against the repo state each
package was built on. Started at pkg32; earlier packages are recorded in
CHANGELOG.md and their README-INTEGRATION files.

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
