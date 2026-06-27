# SiftEntry Pilot Runbook

This runbook keeps the pilot path clear while the product moves from the
Streamlit demo into the Next.js + FastAPI SaaS foundation.

## Repository Layout

- `apps/web/` - Next.js product UI.
- `ez_invoice_app/backend/` - FastAPI API, auth, profiles, invoices, posting logs.
- `ez_invoice_app/` - Streamlit demo app and local connector utilities.
- `ez_invoice_app/data/` - Local SQLite database and uploaded pilot PDFs.
- `docs/decisions/` - Architecture and branding decisions.

## Local Development

Run the API:

```bash
cd "/Users/uditparekh/Documents/Ez Invoice"
PYTHONDONTWRITEBYTECODE=1 python3 -m uvicorn ez_invoice_app.backend.main:app --reload --port 8000
```

Run the Next.js app:

```bash
cd "/Users/uditparekh/Documents/Ez Invoice/apps/web"
PATH="$HOME/.nvm/versions/node/v26.4.0/bin:$PATH" pnpm dev
```

Open:

- Next.js UI: `http://127.0.0.1:3000/login`
- FastAPI docs: `http://127.0.0.1:8000/docs`
- Streamlit demo: `python3 -m streamlit run ez_invoice_app/app.py --server.port 8506`

## Demo Accounts

Use only pilot/demo passwords in the local SQLite database. Do not place
production ERP secrets in exported profile JSON.

- Main demo user: `udit@example.com`
- Neel pilot user: `neelgada321@gmail.com`

## Client Profile Workflow

Client profiles are the source of truth for posting behavior.

Each profile stores:

- Accounting system: Tally, QuickBooks, Zoho Books, or export package.
- Country and default currency.
- Invoice format and parser preference.
- Tax mode and tax labels.
- Posting mode: accounting voucher, item invoice, supplier bill, export package.
- Exact ledger, tax ledger, TCS, round-off, stock item, UOM, and godown names.
- Connector/API metadata.

Recommended flow:

1. Create or import a profile from the Integrations page.
2. Confirm exact ERP names with the client.
3. Mark the profile as default for that accounting system.
4. Upload invoices.
5. Let profile recommendation select the best profile, or manually choose one.
6. Review extracted fields and save corrections.
7. Validate.
8. Post.
9. Review posting logs and retry failed attempts from the invoice detail page.

## Posting Ownership

Posting must be profile-owned end to end. The selected profile controls:

- Tally company, voucher mode, ledgers, item names, GST/TCS/round-off behavior.
- QuickBooks account mappings and supplier Bill payload.
- Zoho organization/account/tax metadata.
- Connector settings and retry history.

If a profile is selected, the UI sends `client_profile_id`; the backend resolves
the target system and builds the accounting payload from that profile.

## Demo-Ready Features

- Authenticated Next.js UI backed by FastAPI.
- Organization-scoped invoice upload and queue.
- Client profile create/edit/default/delete/import/export.
- Team invite management, member visibility, and password change.
- Profile recommendation based on invoice country, currency, tax format, and
  accounting target.
- Side-by-side invoice review with PDF preview and editable extracted fields.
- Correction learning signals from saved field edits.
- Validation, approval, posting, posting logs, and retry.
- QuickBooks, Tally, and Zoho posting foundations.
- Streamlit demo preserved for existing client demos.

## Production Hardening Still Needed

- PostgreSQL with migrations and backups.
- Encrypted secret storage for OAuth tokens and connector tokens.
- Password reset email delivery, role editing, member deactivation, and audit export.
- Rate limiting, login throttling, and production session policies.
- Hosted document storage with signed URLs.
- Queue workers for OCR/parsing/posting jobs.
- Client installer or managed connector for Tally desktop environments.
- Automated parser evaluation against client invoice samples.

## Pilot Packaging

For client handoff, send:

- The clean project folder.
- `ez_invoice_app/CLIENT_WINDOWS_SETUP.md`.
- `ez_invoice_app/TALLY_DEMO_CHECKLIST.md`.
- A client profile export JSON when the profile is ready.
- Only non-secret sample PDFs.

For Gmail-safe delivery, send a Drive link or GitHub private repository invite
instead of attaching a ZIP containing Python files.
