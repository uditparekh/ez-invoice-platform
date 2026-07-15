# Changelog

All notable platform changes will be recorded here.

## [Unreleased]

### Changed

- Home redesigned as a calm work tray: dated greeting summarizing how many
  things need attention, the Sift mode hero card (count + amount in
  flight), a glanceable stat-pill row (needs review, awaiting approval,
  exceptions — each a one-tap filter), an action list that only shows
  rows needing work, and a quiet weekly footer; the ROI hero (auto-
  extracted %, processed value, time saved) moved to the Insights
  overview tab, keeping the daily view about doing and the insights view
  about analyzing

### Changed

- Home as launchpad: a Sift mode hero card shows the live count of
  pending invoices and launches the one-keypress triage flow; the
  Exceptions metric deep-links into the invoice queue with the failed
  filter preselected (the queue now honors a ?status= query parameter)

### Changed

- Workspace simplification: the Integrations page shows only the
  accounting system configured in the workspace's client profiles (the
  platform owner still sees every posting path); the invoice queue gains
  quick filter chips (All, Needs review, Exceptions with live count)

- Mobile pass, phase 2: Rules mapping editor, GL-mapping, Exceptions, and
  Analytics vendor tables all render as cards on phones (desktop keeps
  the full tables); Rules cards use labeled inputs for thumb-friendly
  editing. Audit confirmed the client-profiles panel and review split
  view were already responsive.

### Changed

- Mobile professional pass: posting history renders as cards on phones
  (full table remains on desktop); invoice line items become editable
  cards on phones instead of a sideways-scrolling table; team roster rows
  stack on small screens; workspace dropdown panels clamp to the viewport
  so they never clip on narrow phones; header gains a mobile search button
  (command palette); installed-PWA mode now respects iPhone/Android
  safe-area insets (notch and home indicator)

### Added

- `resend` email provider: sends invitations and password resets through
  Resend's HTTPS API (port 443) instead of SMTP, which Railway blocks or
  disrupts; configure with `EZ_EMAIL_PROVIDER=resend` + `EZ_RESEND_API_KEY`
  (4 new tests)

### Fixed

- Sign-in button no longer drops its "Signing in" spinner before navigation
  completes; the idle-button dead time after a successful login was the main
  perceived lag on the hosted app

### Added

- Railway background worker service config (`railway.worker.json`) so batch
  posting jobs are actually executed in the hosted pilot
- Resend inbound email bridge route (`/api/inbound/resend`): verifies the
  Svix webhook signature, downloads PDF attachments via the Resend
  Attachments API, and forwards them to the backend inbound intake; inert
  until its environment variables are configured
- Pilot infra checklist: worker service setup, Railway spend limit, Resend
  outbound SMTP and inbound bridge configuration, uptime monitoring, and
  provider signup order
- Full pilot QA harness (`tests/pilot_e2e_qa.py`): 42-check end-to-end run
  covering the complete two-client lifecycle on a throwaway database

### Fixed

- Standalone worker (`python -m siftentry_app.backend.worker`) crashed on
  first poll because app state (repository/storage/adapters) is wired inside
  the FastAPI lifespan, which no ASGI server runs for the worker; the worker
  now enters the lifespan context explicitly — this is the exact entrypoint
  the Railway worker service runs
- Hosted Tally posting/dry runs no longer fail with a confusing
  "Connector import failed: 127.0.0.1:8765 connection refused": client
  profiles without a machine-local bridge URL now explicitly disable the
  legacy local-connector default, which only applies when the Streamlit
  pilot runs on the same computer as the connector

- Login now follows the validated `?next=` path the middleware sets
  (internal `/app` paths only), instead of always landing on `/app/invoices`
- Railway build uses Python 3.12 to match the version the test suite runs on

### Fixed (review pass)

- Backend no longer requires Streamlit: `tally_integration`, `qb_integration`,
  and `zoho_integration` import Streamlit optionally with a headless fallback,
  so API and worker containers built from `requirements-api.txt` start and
  post correctly (QuickBooks/Zoho report "not connected" cleanly instead of
  crashing when no pilot session exists)
- `db.create_database_if_missing` builds the Postgres admin URL from the
  parsed path instead of `str.replace`, which corrupted URLs where the
  database name also appeared in the username
  (e.g. `postgresql://siftentry:pw@host/siftentry`)
- Web BFF proxy forwards `Content-Disposition`, preserving the original
  filename when downloading invoice PDFs

### Quality

- Full-repo review pass: removed dead imports and unused exception bindings
  across backend, pilot, and tests (ruff E9/F401/F811/F821 clean); verified
  54/54 Python tests, TypeScript typecheck 0, ESLint 0, and production build
  41/41 routes

### Added

- Next.js 16 customer application under `apps/web`
- Secure same-origin web API boundary with HTTP-only access and refresh cookies
- Login, logout, protected routes, and automatic FastAPI token rotation
- Organization-aware responsive application shell
- Functional invoice queue, status filtering, search, PDF upload, detail view,
  validation display, and line-item table
- Light and dark operational themes with mobile navigation
- SiftEntry customer-facing brand system with ink, indigo, cyan, slate, and
  finance status colors

### Quality

- Strict TypeScript, ESLint, production build, desktop/mobile browser review,
  multi-invoice selection checks, and existing Python test coverage

## [0.2.0] - 2026-06-19

### Added

- FastAPI backend with a universal invoice model and persistent queue
- Organization-scoped users and memberships
- Argon2 password hashing
- JWT access tokens and rotating refresh sessions
- Owner, admin, accountant, approver, and viewer permissions
- Invitation-based workspace access
- Streamlit-to-FastAPI upload, validation, queue, and posting-audit bridge
- QuickBooks, TallyPrime, and Zoho Books posting support
- Cross-organization and role-permission tests

### Changed

- QuickBooks local OAuth callback moved to port `8003`
- Streamlit retained as the working pilot during the Next.js migration

### Security

- Organization and invoice endpoints now require authenticated membership
- Client databases, uploaded PDFs, OAuth settings, and generated packages are
  excluded from Git
