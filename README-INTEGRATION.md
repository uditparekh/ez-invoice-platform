# SiftEntry — Invoice Activity Timeline (July 19, 2026)

## What this adds
Every invoice detail view now ends with an "Activity" section: a vertical
audit trail showing when the invoice was uploaded (with filename), every
field correction with who made it and when, and every posting attempt —
dry runs, successes (green), failures (red) with the error message.
This is the audit story clients can see with their own eyes.

Note: it includes the /health HEAD fix commit only if you already shipped
it — this package touches main.py, and it was built on top of your latest
commit 942f340, so it already CONTAINS the HEAD fix. Safe to apply.

## Files (6)
| # | File | Change |
|---|------|--------|
| 1 | siftentry_app/backend/main.py | New GET /api/v1/invoices/{id}/activity endpoint |
| 2 | siftentry_app/backend/repository.py | list_corrections_for_invoice method |
| 3 | apps/web/src/app/api/invoices/[invoiceId]/activity/route.ts | New BFF route |
| 4 | apps/web/src/components/invoices/invoice-detail.tsx | ActivityTimeline section |
| 5 | CHANGELOG.md | Entry |
| 6 | README-INTEGRATION.md | This note |

## Steps
1. GitHub Desktop → Pull first (built on commit 942f340).
2. Unzip over repo root. Diff check: main.py one green block (the new
   endpoint), repository.py one green block, route.ts brand new file,
   invoice-detail.tsx two green blocks (component + its render call).
3. Commit: Invoice activity timeline
4. Push — Railway (API) and Vercel (web) both redeploy.

## Verify
Open any invoice → scroll below line items → "Activity" card shows at
least "Invoice uploaded · <filename>". Make a correction in review, save,
reopen → the correction appears with your name. Run a dry-run post → it
appears too. The section hides itself on invoices with no events yet
while loading — brief blankness then appearing is normal.
