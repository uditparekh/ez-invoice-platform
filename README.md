# SiftEntry Platform

SiftEntry is an invoice-to-ledger automation platform for modern finance teams.
It extracts, reviews, validates, approves, and posts supplier invoices to
accounting systems. The current pilot supports QuickBooks Online, TallyPrime,
and Zoho Books.

This repository is the single source of truth for the platform. The proven
Streamlit pilot remains available while the customer-facing Next.js
application is developed alongside it.

## Repository Layout

```text
apps/
  web/                    Next.js customer application
ez_invoice_app/
  app.py                  Existing Streamlit pilot
  backend/                FastAPI API, authentication, and tenant isolation
  *_integration.py        Accounting-system connectors
tests/                    Python API, repository, domain, and isolation tests
docs/
  decisions/              Architecture decision records
scripts/                  Development and release helpers
```

## Current Capabilities

- Universal PDF invoice extraction with GST/e-Invoice support
- Multi-tenant FastAPI backend
- Argon2 password hashing and JWT authentication
- Rotating and revocable refresh sessions
- Owner, admin, accountant, approver, and viewer roles
- Organization-level invoice isolation
- QuickBooks Bill posting
- TallyPrime purchase-voucher posting through a local connector
- Zoho Books Bill posting
- Streamlit invoice queue, history, analytics, and integration settings
- SiftEntry Next.js login, organization-aware shell, invoice queue, search, filtering,
  PDF upload, invoice selection, and line-item review
- Same-origin web API boundary with secure HTTP-only session cookies

## Local Development

Install Python dependencies:

```bash
python3 -m pip install -r ez_invoice_app/requirements.txt
```

Copy `.env.example` values into your shell or a private `.env` file. Never
commit real credentials.

Start FastAPI:

```bash
export EZ_API_JWT_SECRET="replace-with-a-long-random-secret"
python3 -m uvicorn ez_invoice_app.backend.main:app --reload --port 8000
```

Start the Streamlit pilot in a second terminal:

```bash
export EZ_INVOICE_BACKEND="api"
export EZ_API_EMAIL="owner@ezinvoice.local"
export EZ_API_PASSWORD="replace-with-your-local-password"
python3 -m streamlit run ez_invoice_app/app.py --server.port 8506
```

Start the Next.js application in another terminal:

```bash
cd apps/web
cp .env.example .env.local
pnpm install
pnpm dev
```

Open:

- Next.js application: `http://127.0.0.1:3000`
- Streamlit pilot: `http://127.0.0.1:8506`
- FastAPI documentation: `http://127.0.0.1:8000/docs`

## Tests

```bash
python3 -m pytest -q
cd apps/web
pnpm lint
pnpm typecheck
pnpm build
```

## Versioning

Working releases are tagged in Git. Generated client ZIP packages are release
artifacts and are intentionally excluded from source control.

See [CHANGELOG.md](CHANGELOG.md) and
[docs/decisions](docs/decisions) for development history and architectural
decisions.
