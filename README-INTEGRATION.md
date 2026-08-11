# pkg32 — Voucher with stock allocation, connector guard, PWA build refresh

Built against: main @ e76a514 ("Docs: fix stale api.siftentry.com hostname
references"). Verify your local main is at this commit before applying. If it
is not: STOP and tell me the current commit.

## Files in this zip: 15 total (12 changed, 3 new)

Apply by copying each file to the same path in the repo. No apply-order
dependency — all files are independent copies. Overwrite when prompted.

Backend (4 changed):
1.  siftentry_app/backend/models.py
2.  siftentry_app/tally_integration.py
3.  siftentry_app/backend/adapters.py
4.  siftentry_app/backend/main.py

Tests (2 changed):
5.  tests/test_tally_integration.py
6.  tests/test_api.py

Web (4 changed, 2 new):
7.  apps/web/src/lib/types.ts
8.  apps/web/src/components/client-profiles/profile-wizard.tsx
9.  apps/web/src/components/client-profiles-panel.tsx
10. apps/web/src/app/layout.tsx
11. apps/web/src/app/api/system/build/route.ts          (NEW — create folder)
12. apps/web/src/components/build-refresh.tsx           (NEW)

Docs (2 changed, 1 new):
13. CHANGELOG.md
14. README-INTEGRATION.md (this file)
15. SIFTENTRY_CHANGELOG.md                              (NEW)

## What this package delivers

1. Tally "Voucher with stock allocation" posting mode — the third posting
   shape, for your pilot client: looks like a Dr/Cr accounting voucher in
   Tally (ISINVOICE=No) but stock still updates through
   INVENTORYALLOCATIONS.LIST nested inside each purchase ledger debit.
   Lines are grouped by purchase ledger, so it is correct whether the
   client uses one purchase ledger or several. Selectable in the wizard
   (now three cards) and the profile editor dropdown. Stock item / UOM /
   godown preflight applies to it exactly like Item Invoice.
2. Golden XML tests for all three posting modes — build_tally_xml had zero
   test coverage before this package. Each test also asserts the OTHER
   modes' markers are absent, so a mode emitting the wrong shape fails.
3. Connector double-posting guard — a second connector-enabled Tally
   profile per organization is rejected with 409 naming the conflicting
   profile (on create and on update). The error message surfaces as-is in
   the existing profile save notice; no frontend change was needed for it.
4. PWA build refresh — GET /api/system/build returns the deployed build id
   with no-store headers; a BuildRefresh component in the root layout polls
   it every 60s (and on tab focus) and reloads once when a new deployment
   lands. Installed PWAs pick up fixes without a manual hard refresh.
   There is deliberately no service worker.

## Diff expectations in GitHub Desktop

- models.py: one green line inside ProfilePostingMode.
- tally_integration.py: green blocks around _posting_mode (alias sets +
  helpers), a large green block adding _build_voucher_inventory_entries,
  a green envelope branch inside build_tally_xml, and two SMALL red blocks:
  the item-invoice branch condition (inline set → helper call) and the
  preflight is_item_invoice set (inline set → shared constants). If you see
  red inside the existing Item Invoice or Accounting Voucher envelope
  strings: STOP.
- adapters.py: small red block replacing the posting_mode ternary with a
  label-map lookup, plus a green map above the function.
- main.py: green import line, green constants block, green guard function,
  green inserts in create/update profile endpoints, and a small red block
  in the profile preflight (item_invoice check → INVENTORY_POSTING_MODES,
  plus one message wording line). If you see red anywhere else in main.py:
  STOP.
- test_tally_integration.py: one green import line + green tests appended.
- test_api.py: green-only appended tests.
- types.ts: one green line in the ProfilePostingMode union.
- profile-wizard.tsx: green import line, small red block widening the
  voucherMode type + green label map, a red/green block replacing the
  two-card grid with three cards, one red/green line in the review step.
- client-profiles-panel.tsx: one green dropdown line, one small red/green
  block widening isItemInvoice.
- layout.tsx: green import + small red/green block in the body.
- build/route.ts and build-refresh.tsx: entirely new files (all green).
- CHANGELOG.md / SIFTENTRY_CHANGELOG.md: green only.

## Commit message

Tally voucher-with-stock-allocation mode, connector double-posting guard, PWA build refresh

## Verify steps

1. Backend: `python3 -m pytest -q` → 86 passed (was 75).
2. Web, from apps/web: `pnpm typecheck && pnpm lint && pnpm build` → all
   clean; the build route list includes /api/system/build (43 routes
   total, was 42).
3. Push via GitHub Desktop, confirm the latest commit message at
   github.com/uditparekh/ez-invoice-platform, let Railway + Vercel deploy.
4. Open app.siftentry.com → Client profiles → New client profile wizard →
   step 3 shows THREE posting-mode cards including "Voucher with stock
   allocation".
5. Guard check: on an org that already has a connector-enabled Tally
   profile, try creating a second Tally profile with the connector toggle
   on → the save is rejected and the notice names the existing profile.
6. Build refresh check (after the NEXT deploy following this one): leave
   the installed PWA open through a deploy; within ~60s of the new
   deployment going live it reloads itself once.

## For the pilot client's profile

Set posting mode to "Voucher with stock allocation". Before the first live
post, still confirm with the client: (a) one purchase ledger or several
(the XML handles both; this is verification), and (b) whether Tally prompts
for a godown/batch during their allocation entry — if yes, put the exact
godown name in the profile; if no, leave godown blank.
