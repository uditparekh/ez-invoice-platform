# EZ-Invoice API Foundation

The existing Streamlit application remains the working pilot interface. The
new FastAPI package provides the stable backend contract for a future React or
Next.js frontend.

## Current Boundary

```text
Streamlit pilot
    |
Authenticated FastAPI organization, client profile, upload, validation, queue, and audit APIs
    |
SQLite repository + local PDF storage
    |
Streamlit QuickBooks / Tally / Zoho posting during transition
    |
Posting result callback to FastAPI
```

The API currently runs as a modular monolith. This is intentional: it keeps
deployment and debugging simple while establishing clear module ownership.

## Backend Modules

- `backend/models.py`: API and domain models, including organization-scoped
  client profiles for accounting-system setup.
- `backend/domain.py`: conversion between legacy parser payloads and the
  universal invoice model.
- `backend/parser_service.py`: PDF text extraction and parser routing without
  Streamlit session state.
- `backend/repository.py`: organizations, client profiles, invoices, lines,
  corrections, mappings, posting attempts, and audit events.
- `backend/adapters.py`: uniform wrappers over QuickBooks, Tally, and Zoho.
- `backend/main.py`: HTTP endpoints and workflow rules.

## Run Locally

From the directory containing `ez_invoice_app`:

```bash
python3 -m pip install -r ez_invoice_app/requirements.txt
python3 -m uvicorn ez_invoice_app.backend.main:app --reload --port 8000
```

Open:

- API documentation: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`

The Streamlit pilot can run at the same time:

```bash
python3 -m streamlit run ez_invoice_app/app.py --server.port 8506
```

The bridge defaults to `EZ_INVOICE_BACKEND=auto`. Set it to `api` to require
FastAPI or `legacy` to temporarily restore the original in-memory workflow.
The API URL defaults to `http://127.0.0.1:8000`.

## Core Workflow

1. Create an organization.
2. Create or select a client profile for the target accounting system.
3. Upload or import an invoice.
4. Review and patch extracted fields.
5. Validate the invoice.
6. Approve it.
7. Post to QuickBooks, Tally, or Zoho Books.
8. Read the posting result and audit trail.

## Client Profiles

Client profiles store the accounting-system setup that should not be hardcoded
inside parsers or posting adapters. Each organization can maintain separate
profiles for Tally, QuickBooks, Zoho Books, and future systems. A profile can
capture company names, voucher modes, purchase/tax/TCS/round-off ledgers,
stock item mappings, parser preference, connection metadata, and a default flag
per accounting system.

The first API slice supports:

- `GET /api/v1/organizations/{organization_id}/client-profiles`
- `POST /api/v1/organizations/{organization_id}/client-profiles`
- `GET /api/v1/organizations/{organization_id}/client-profiles/{profile_id}`
- `PATCH /api/v1/organizations/{organization_id}/client-profiles/{profile_id}`
- `POST /api/v1/organizations/{organization_id}/client-profiles/{profile_id}/set-default`
- `DELETE /api/v1/organizations/{organization_id}/client-profiles/{profile_id}`

## Important Transitional Constraint

QuickBooks and Zoho authentication currently live in Streamlit session state.
During this bridge phase, Streamlit performs those proven posting calls and
submits the success or failure result to FastAPI for status and audit
persistence. Production deployment requires moving OAuth tokens into encrypted
organization-scoped server storage so FastAPI workers can own posting. Tally
can continue through the local connector while its job polling protocol is
moved to the cloud API.

## Next Backend Milestones

Authentication, rotating refresh sessions, memberships, invitations, and
role-based tenant isolation are now implemented. The next milestones are:

1. Use saved client profiles inside posting adapters and the Streamlit/Next.js
   posting flow.
2. React/Next.js login, organization switcher, invoice queue, client profile
   settings, and review console.
3. PostgreSQL migration and Alembic migrations.
4. Encrypted organization-scoped integration credential storage.
5. Background extraction and posting jobs.
6. Signed object-storage URLs for PDFs.
7. Side-by-side PDF review endpoints and extraction evidence.
