# SiftEntry Project Map

This file is the working map for what exists, where it lives, and what is still
in progress. Keep it short and current.

## Current Structure

| Area | Path | Purpose |
|---|---|---|
| Next.js product app | `apps/web/` | Modern SaaS UI, auth screens, invoice queue, analytics, history, settings, integrations |
| FastAPI backend | `siftentry_app/backend/` | Auth, organizations, invoices, client profiles, review, posting logs, API endpoints |
| Streamlit pilot | `siftentry_app/app.py` | Existing demo app kept for client demos while Next.js reaches parity |
| Parsers | `siftentry_app/*parser*.py`, `siftentry_app/backend/parser_service.py` | PDF text extraction, GST/e-Invoice parsing, universal parsing, AI/OCR assisted layer |
| Accounting adapters | `siftentry_app/qb_integration.py`, `siftentry_app/tally_integration.py`, `siftentry_app/zoho_integration.py`, `siftentry_app/backend/adapters.py` | QuickBooks, Tally, Zoho posting/export logic |
| Tally connector | `siftentry_app/tally_connector_*.py`, `packaging/windows/tally-connector/` | Local Windows bridge for TallyPrime desktop |
| Tests | `tests/` | API, parser, repository, Tally connector, and adapter verification |
| Docs | `docs/`, `siftentry_app/*.md` | Runbooks, production notes, connector setup, architecture decisions; start with `docs/INDEX.md` |
| Brand/UI assets | `brand/` | SiftEntry logo, color, and visual system references |
| Packaging | `packaging/windows/` | Windows Tally connector packaging and release assets |

## File Ownership Rules

Use these rules before adding new files:

| New work | Put it here | Notes |
|---|---|---|
| Product UI screens, shared UI components, hooks, and browser API wrappers | `apps/web/src/` | Keep the Next.js app independent from Streamlit UI code. |
| FastAPI routes, auth, persistence, storage, review, posting orchestration | `siftentry_app/backend/` | Backend owns tenant boundaries, profile-owned posting, logs, and retention. |
| Streamlit demo-only UI and legacy pilot helpers | `siftentry_app/app.py` and nearby Streamlit helpers | Preserve the pilot while Next.js reaches complete feature parity. |
| Reusable accounting-system logic | `siftentry_app/*_integration.py`, `siftentry_app/backend/adapters.py` | Avoid client-specific hardcoding; use client profiles for names, ledgers, and tax behavior. |
| PDF parsing and AI/OCR extraction logic | `siftentry_app/*parser*.py`, `siftentry_app/backend/parser_service.py`, `siftentry_app/backend/ai_parser.py` | Parser output should stay universal and feed profile recommendation/corrections. |
| Tally desktop connector runtime | `siftentry_app/tally_connector_*.py` | Runtime source stays with the Python app because clients run it locally. |
| Windows installer/build files | `packaging/windows/tally-connector/` | Keep packaging separate from runtime connector code. |
| Cross-project runbooks and roadmap docs | `docs/` | Put production, deployment, connector, and roadmap docs here. |
| Pilot-specific client setup docs | `siftentry_app/*.md` | Keep these beside the Windows `.bat` scripts they reference. |
| Brand and visual references | `brand/` | Source of truth for SiftEntry logo/color examples; not runtime app code. |
| Tests | `tests/` | Add regression tests with every backend/parser/accounting behavior change. |

Do not commit local runtime artifacts: `.env` files, SQLite databases,
uploaded PDFs, `.next`, `node_modules`, `.pnpm-store`, `__pycache__`,
pytest caches, generated ZIPs, connector build folders, or packaged binaries.

## File Count Snapshot

- Python files: 33
- Next.js TypeScript/TSX source files: 95
- Python app dependency file: `siftentry_app/requirements.txt`
- Next.js dependency file: `apps/web/package.json`
- Windows connector dependency file: `packaging/windows/tally-connector/requirements.txt`

## Run Commands

From the repository root:

```bash
make install-python
make install-web
make api
make bootstrap
make web
```

Open:

- Product UI: `http://127.0.0.1:3000/login`
- API docs: `http://127.0.0.1:8000/docs`
- Streamlit demo: `make streamlit`, then `http://127.0.0.1:8506`

Default local demo account created by `make bootstrap`:

- Email: `udit@example.com`
- Password: `local-demo-password-123`

If the database already has users, bootstrap returns a conflict. Use the
existing local account, or intentionally reset the local database outside Git.

## Current Product Status

### Done / Working Foundation

- FastAPI backend with JWT auth, org memberships, roles, invite/reset plumbing.
- Next.js app shell, login, invoice queue, history, analytics, settings, and integration pages.
- PDF upload into backend with preview-only demo mode.
- PDF retention metadata with SHA-256 hashes, review-window cleanup, paid 90-day retention policy support, and invoice history preserved after document deletion.
- Client profiles with accounting-system settings, training profile data, and profile-owned posting configuration.
- Client onboarding wizard for accounting setup, sample invoices, generated recommendations, admin review, and activation.
- Profile recommendation by country, currency, tax format, and accounting target.
- QuickBooks, Tally, and Zoho posting foundations.
- Posting logs and retry history owned by backend.
- Tally connector desktop/runtime foundation.
- AI/OCR assisted parser mode v1 with provider selection, profile-context fallback, webhook contract, and status endpoint.
- Invoice review workspace v1 with PDF preview, editable extracted fields, correction capture, line-item review, and parser evaluation hooks.
- Tally purchase-voucher and item-invoice XML v1 controlled by client profile, including GST/IGST/CGST/SGST, TCS, round-off, godown, stock item, HSN, and UOM fields.
- Repository structure consolidated into a monorepo map with clear ownership for Next.js, FastAPI, Streamlit pilot, accounting adapters, packaging, docs, tests, and ignored runtime artifacts.

### Started, Not Final

- External AI/OCR extraction: provider contract exists, but no paid/provider OCR model is configured.
- Parser evaluation: stored in invoice payload and visible in review flows; batch score views still need work.
- Saved corrections/vendor learning: correction signals exist; automatic vendor-specific parser tuning is next.
- Tally hardening: profile-controlled fields exist; needs more live edge-case testing with Neel, Crescent, and new client invoices.
- Production deployment: pilot docs exist; Postgres, hosted object storage, scheduled lifecycle cleanup, encrypted secrets, workers, and real email need final implementation.

## Next Practical Milestones

1. Verify the current local platform end to end with one invoice upload and one client profile activation.
2. Add a real OCR/LLM provider behind `SIFTENTRY_AI_PROVIDER=webhook` and `SIFTENTRY_AI_EXTRACTOR_URL`.
3. Turn correction history into automatic vendor/profile learning.
4. Harden Tally item-invoice XML against more live Neel, Crescent, and future client samples.
5. Prepare deployable pilot environment with persistent DB/object storage, scheduled retention cleanup, SMTP, secrets, and background workers.
6. Package and release the Windows Tally connector for pilot clients.
