# Changelog

All notable platform changes will be recorded here.

## [Unreleased]

### Changed

- Mobile navigation and header polish: the hamburger button is now a
  44px bordered icon button (previously a 36px borderless ghost that
  was easy to miss), the drawer close and mobile search buttons match
  the same icon-button language and touch-target size, the sign-out
  button gets a coherent resting state with a danger-tinted hover (the
  standard destructive affordance), and the theme toggle collapses to
  icon-only segments on phones so the header breathes at 360px

### Changed

- Design-system consolidation: eliminated every hardcoded color in the
  app (40 → 0). The Sift review workspace — built "always dark" by
  hand-pasting the dark token values — is now scoped with the dark
  token set and uses semantic classes throughout, so it stays in
  lockstep with the locked UI spec; the training-hero gradient (shared
  by Home) and the analytics accent gradients are named tokens in
  globals.css (--hero-from/-via/-to, --accent-grad-via/-to,
  --stat-on-dark) instead of scattered literals

### Changed

- Client-facing copy pass before pilot onboarding: accounting system
  badges now read "Live" instead of "Pilot ready"; the posting workflow
  checklist no longer repeats an internal filler sentence under every
  step; the checklist subtitle, Tally notes, and Zoho card drop
  owner-voice pilot language for neutral product copy

### Added

- Weekly email digest: the Settings → Notifications "Weekly digest"
  toggle now works — every Monday at 03:00 UTC (08:30 IST) the worker
  emails each active member of workspaces with the toggle on: invoices
  received in the last 7 days, posted count and value by currency,
  failed postings, what needs review/approval/posting now, supplier
  formats still in training, and any configured Tally connector that is
  offline; quiet workspaces are skipped, a per-organization digest.sent
  audit event prevents duplicates across restarts, and the day/hour are
  overridable via SIFTENTRY_DIGEST_DAY / SIFTENTRY_DIGEST_HOUR_UTC
  (3 new tests)

### Added

- Tally connector heartbeat and live status: the connector now reports
  its host, version, and Tally state on every poll; a new
  POST /api/v1/connectors/tally/heartbeat keeps it visible even while
  TallyPrime is closed; and a new
  GET /api/v1/organizations/{id}/connectors/tally/status powers the
  Integrations → Tally page's live "Windows connector status" card —
  Connected/Disconnected badge, last check-in, Tally company, connector
  machine and version, and last posting outcome, auto-refreshing every
  15 seconds (1 new test, connector_heartbeats table auto-creates on
  both SQLite and PostgreSQL)

- Client connector kit: packaging/client-kit builds
  SiftEntry-Tally-Connector-Kit.zip (served at
  /downloads/SiftEntry-Tally-Connector-Kit.zip and linked from the
  Tally integration page) — the connector modules, one-time setup and
  start scripts, optional Windows-startup install, and a plain-language
  README-START-HERE.txt an accountant can follow end to end

### Changed

- Connector runtime v0.3.0 (now matching the Windows installer):
  cloud-polling mode only needs the requests package (Flask is optional,
  legacy local-API mode only), the CLI reuses settings saved once in the
  status window, and RUN_TALLY_CONNECTOR_WINDOWS.bat starts cloud
  polling against https://app.siftentry.com; TALLY_DEMO_CHECKLIST.md
  rewritten for the production flow

### Removed

- The Integrations → Tally "Local connector" test card and its
  /api/integrations/tally/test-connector route — they tried to reach
  the connector at 127.0.0.1 from Vercel's servers, which can never
  work in production; the heartbeat-driven status card replaces them

### Added

- Training mode UI (Phase B): the Client profiles page shows the format
  registry — a training hero with the count of trusted vs in-training
  formats and a Train formats action, a "new formats detected" callout,
  and a format collection where each supplier shows its Trusted badge or
  a Training progress bar (clean streak out of five); the invoice queue
  surfaces a "New format detected — train it" banner whenever invoices
  arrive from suppliers with no training record

### Added

- Training mode (Phase B backend): a supplier format registry tracks every
  supplier's invoice format per organization; each approved invoice with
  zero corrections extends that format's clean streak, any correction
  resets it, and five consecutive clean approvals graduate the format
  from `training` to `trusted` (corrections demote trusted formats back);
  GET /api/v1/organizations/{id}/supplier-formats returns all formats
  plus a "new formats detected" feed of suppliers with no training record
  (3 new tests)

### Added

- Invoice activity timeline: every invoice detail now shows its audit
  trail — upload, each field correction with the person who made it, and
  every posting attempt (dry runs, successes, failures) — served by a new
  GET /api/v1/invoices/{id}/activity endpoint

### Fixed

- /health answers HEAD requests (uptime checkers such as UptimeRobot
  probe with HEAD by default; the previous 405 read as downtime)

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
