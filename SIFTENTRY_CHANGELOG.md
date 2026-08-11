# SiftEntry Cumulative Package Changelog

Tracks every file changed per delivered package, against the repo state each
package was built on. Started at pkg32; earlier packages are recorded in
CHANGELOG.md and their README-INTEGRATION files.

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
