# EZ-Invoice

EZ-Invoice is a Streamlit invoice intake platform built from the provided reference app.
It uses dynamic document extraction adapters plus a generic supplier invoice parser,
then routes validated invoices into QuickBooks, TallyPrime, Coupa, NetSuite, and SAP.

## Client Workspace Model

Each customer should operate inside its own EZ-Invoice workspace. The client
logs in, saves its legal entity aliases, connects its accounting system, uploads
supplier invoices, reviews extracted data, and posts approved inbound bills into
its own Tally company.

The local prototype stores a single client workspace profile. The SaaS version
should move this into a tenant database with users, roles, connector secrets,
ledger mappings, approval status, and posting history.

## Run

On Windows, open Command Prompt inside this folder and run:

```bat
py -m pip install -r requirements.txt
py -m streamlit run app.py --server.port 8506 --server.address 127.0.0.1
```

Then open `http://127.0.0.1:8506` in Chrome or Edge.

You can also double-click `INSTALL_PACKAGES_WINDOWS.bat`, then
`RUN_EZ_INVOICE_WINDOWS.bat`.

## FastAPI Backend

The first SaaS backend slice now lives in `backend/`. It adds a universal
invoice model, SQLite persistence, local PDF storage, validation, corrections,
audit events, and posting adapters for QuickBooks, Tally, and Zoho Books.

From the folder containing `ez_invoice_app`, run:

```bash
python3 -m pip install -r ez_invoice_app/requirements.txt
python3 -m uvicorn ez_invoice_app.backend.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000/docs` for the interactive API documentation.
The Streamlit pilot and the API should run at the same time during the
frontend migration:

```bash
# Terminal 1
python3 -m uvicorn ez_invoice_app.backend.main:app --reload --port 8000

# Terminal 2
python3 -m streamlit run ez_invoice_app/app.py --server.port 8506
```

With FastAPI available, Streamlit automatically uses it for organization
creation, PDF upload, validation, invoice queue persistence, queue clearing,
and posting audit results. If FastAPI is unavailable, the default `auto` mode
temporarily falls back to the legacy in-memory workflow.

Optional bridge settings:

```bash
export EZ_INVOICE_BACKEND="api"       # api, auto, or legacy
export EZ_API_BASE_URL="http://127.0.0.1:8000"
export EZ_ORGANIZATION_NAME="Client Workspace"
export EZ_API_EMAIL="owner@ezinvoice.local"
export EZ_API_PASSWORD="local-development-password"
```

Use `EZ_INVOICE_BACKEND=api` while testing the backend contract because it
shows a visible error instead of silently using the legacy workflow. See
`API_ARCHITECTURE.md` for the migration boundary and next milestones.

## Authentication And Client Isolation

FastAPI now requires authentication for every organization, invoice, workflow,
and posting endpoint. Users receive organization memberships with one of these
roles:

- `owner`: complete workspace and membership control
- `admin`: workspace and membership administration
- `accountant`: upload, edit, validate, and post invoices
- `approver`: review, validate, and approve invoices
- `viewer`: read-only access

For the first local run, Streamlit uses the `EZ_API_EMAIL` and
`EZ_API_PASSWORD` values above. When no users exist and development bootstrap
is enabled, FastAPI creates that owner and attaches it to the matching existing
organization. Later runs use the normal login endpoint.

Before any hosted deployment, set:

```bash
export EZ_API_ENVIRONMENT="production"
export EZ_API_JWT_SECRET="GENERATE_A_LONG_RANDOM_SECRET"
export EZ_API_ALLOW_DEV_BOOTSTRAP="false"
```

Production must provide a unique JWT secret. Refresh sessions are rotating,
revocable, and stored only as token hashes in the database.

Authentication endpoints are available in the FastAPI documentation:

- `POST /api/v1/auth/bootstrap` for the first development owner only
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- organization invitation creation and acceptance

## QuickBooks

Set these as environment variables or Streamlit secrets:

```bash
QB_CLIENT_ID=...
QB_CLIENT_SECRET=...
QB_REDIRECT_URI=http://localhost:8003/callback
QB_ENVIRONMENT=sandbox
QB_USE_LOCAL_CALLBACK=true
```

The redirect URI must exactly match a redirect URI registered in the Intuit
developer app. For production, use `QB_ENVIRONMENT=production`, register an
HTTPS callback URL, and set `QB_USE_LOCAL_CALLBACK=false`. `QB_BASE_URL` is an
optional override; EZ-Invoice selects the correct sandbox or production API
host from `QB_ENVIRONMENT`.

Port `8000` is reserved for FastAPI. Register and use
`http://localhost:8003/callback` for the local QuickBooks OAuth callback.

After connecting, refresh the Chart of Accounts and map the generic invoice
categories (`materials`, `services`, `freight`, `fees`, `tax`, and `general`)
to the client's own QuickBooks expense or cost-of-goods accounts. EZ-Invoice
creates supplier invoices as QuickBooks Bills and prevents the same invoice
number from being posted twice to the connected company.

## Zoho Books

Create a Zoho API Console server-based client and register this development
redirect URI:

```text
http://localhost:8001/zoho/callback
```

For an Indian Zoho Books organization, start EZ-Invoice with:

```bash
export ZOHO_CLIENT_ID="YOUR_ZOHO_CLIENT_ID"
export ZOHO_CLIENT_SECRET="YOUR_ZOHO_CLIENT_SECRET"
export ZOHO_REDIRECT_URI="http://localhost:8001/zoho/callback"
export ZOHO_ACCOUNTS_BASE_URL="https://accounts.zoho.in"
export ZOHO_API_BASE_URL="https://www.zohoapis.in/books/v3"
export ZOHO_USE_LOCAL_CALLBACK="true"
```

Open **Zoho Books** in EZ-Invoice, connect the account, select the client
organization, refresh the Chart of Accounts, and map each universal category.
Select a default purchase tax only when extracted invoice lines contain tax.
EZ-Invoice resolves or creates the vendor, creates a Zoho Books Bill, stores
the returned Bill ID, and prevents the same supplier invoice from being posted
twice to that organization.

For another Zoho data center, replace the Accounts and API hostnames with the
regional domains assigned to the client's Zoho account.

## TallyPrime

1. Open TallyPrime and load the company.
2. Enable the HTTP Server in TallyPrime advanced configuration. The default endpoint is `http://localhost:9000`.
3. In EZ-Invoice, open **Tally**, save the client workspace, connector, and voucher settings, then test the connector.
4. Make sure the vendor and purchase/expense/tax ledgers used by the generated XML exist in TallyPrime before importing.

The app generates accounting purchase vouchers as Tally XML and can either download them or POST them to the TallyPrime HTTP gateway.

For production SaaS, the cloud app should not try to call a client's
`localhost:9000` directly. Run a small client-side EZ-Invoice Tally Connector
beside TallyPrime; it authenticates to EZ-Invoice, receives approved posting
jobs, sends XML to Tally, and returns success/error responses.

## SAP Business One Next

SAP Business One will use the Service Layer rather than the Tally local XML
gateway. A pilot client must provide a test company database, Service Layer
URL, API user, supplier master data, purchase accounts, tax codes, warehouses,
units, and sample item-based and service-based A/P invoices. Credentials must
be stored outside source code.

## Local Tally Connector Prototype

Start the connector on the same Windows computer where TallyPrime is open:

```bat
cd /d "PATH_TO_THIS_FOLDER"
set EZ_TALLY_CONNECTOR_TOKEN=replace-with-a-local-token
py tally_connector_agent.py --workspace-id local-workspace --tally-url http://localhost:9000
```

Or double-click `RUN_TALLY_CONNECTOR_WINDOWS.bat`.

In EZ-Invoice, open **Tally** and use:

```text
Connector URL: http://127.0.0.1:8765
Workspace ID: local-workspace
Connector token: replace-with-a-local-token
```

Click **Save Connector**, **Test Connector**, then **Test Tally via Connector**.

Optional command-line XML export without posting:

```bat
py process_tally_batch.py --direction inbound "C:\path\to\invoice.pdf"
```

Post only when TallyPrime is open, the correct company is loaded, and ledgers are ready.
