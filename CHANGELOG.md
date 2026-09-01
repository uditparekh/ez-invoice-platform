# Changelog

All notable platform changes will be recorded here.

## [Unreleased]

### Added

- Member role changes (pkg33): PATCH
  /api/v1/organizations/{id}/members/{user_id} changes an existing
  member's role in place — previously the only path was re-inviting the
  member. Owner promotion stays owner-only, and the last owner cannot be
  demoted. Team access rows in Settings now carry a role dropdown (your
  own row stays read-only) (3 new tests)
- Collapsible profile library (pkg33): the client-profiles library
  collapses to a slim rail so the editor takes the width. Starts
  collapsed when there is one profile or none, expanded when there are
  several; a manual toggle wins and is remembered per browser. Profiles
  can still be switched from the rail. Below the desktop breakpoint the
  same toggle collapses the list vertically

- Tally "Voucher with stock allocation" posting mode (pkg32): a third
  posting mode for clients who enter purchases in Tally's voucher mode
  (Dr/Cr accounting voucher screen) but allocate stock items through
  the ledger allocation sub-screen. The generated XML posts as
  ISINVOICE=No / Accounting Voucher View with INVENTORYALLOCATIONS
  nested inside each purchase ledger debit, grouped by ledger so both
  single-ledger and split-ledger clients post correctly. Stock item,
  UOM, and godown preflight requirements now apply to both
  inventory-backed modes. Selectable in the onboarding wizard (three
  posting-mode cards) and the client profile editor
- Golden XML tests for all three Tally posting modes (pkg32):
  build_tally_xml previously had no direct test coverage; seven new
  tests pin each mode's discriminating markers (ISINVOICE, voucher
  view, inventory element shape and nesting), debit/credit balance,
  ledger grouping, godown emission, and new-mode preflight
- Connector double-posting guard (pkg32): creating or updating a
  second connector-enabled Tally profile in the same organization is
  rejected with 409 naming the conflicting profile. Connector auth
  matches workspace+token across all Tally profiles and returns the
  first enabled match, so two enabled profiles made claim ownership
  ambiguous and could post the same invoice twice (4 new tests)
- PWA build refresh (pkg32): a no-store /api/system/build endpoint
  exposes the deployed build id, and a client poller (60s interval,
  plus focus/visibility checks) reloads installed PWA sessions once
  when a new deployment lands, so fixes reach clients without a
  manual hard refresh or reinstall. No service worker is involved

### Security

- Public demo hardening: the shared demo account is now read-only at
  the auth layer, not just by role — every mutating request from the
  demo login is rejected with 403 except auth flows (refresh/logout),
  closing the remaining escape hatches: creating a new organization
  (where the demo would have become an owner), accepting invitations,
  and changing the shared demo password. Demo data stays synthetic by
  construction since nothing can be uploaded or modified (1 new test)

### Changed

- Profile editor "Ledgers and stock items" (pkg33): the flat 14-field
  grid is now three concept groups — where purchases post, default stock
  item, item mapping rules — each with one plain sentence of why. Every
  field carries helper text under it instead of example-style
  placeholders that read as filled values; optional fields are labelled
  optional. Stock item settings are hidden for ledger-only posting
  modes. The embedded mapping row is replaced by a rule count and a
  link to Rules & mapping, which is now the single place mappings are
  edited
- AI readiness (pkg33): the percentage score and progress bar are
  replaced by a plain-language status sentence naming what is missing
  or what would improve accuracy. Extraction guidance, validation rules,
  and posting expectations are now correctly labelled recommended, not
  required — the activation gate never required them, and the two
  panels disagreed. The readiness card now sits inside the training
  panel, and each instruction textarea shows its own inline status
  ("Sent with every extraction" / "Optional · improves accuracy")
- Wizard (pkg33): the "Posting expectations" field now saves to
  posting_expectations; it was writing to extraction_instructions

### Fixed

- Root layout viewport (pkg33): viewportFit: "cover" was nested inside
  the light-mode themeColor entry instead of on the viewport object, so
  installed PWAs got no safe-area handling on notched phones
- Removed the orphaned /app/gl-mapping route (pkg33): a demo page with
  hardcoded categories that touched no real profile data and was not
  linked from navigation

- Mobile tab bar (pkg30): the Menu tab moved from the right end to the
  left end of the bottom navigation bar

### Added

- Navigation performance pass (pkg29): workspace invoices are now served
  from a shared stale-while-revalidate cache — switching pages renders
  the last known data instantly while a silent background refresh keeps
  it current, instead of blocking every page behind a full network round
  trip. The cache is cleared on sign-out. A new bulk endpoint
  (`GET /api/v1/organizations/{id}/postings`) replaces the posting log's
  one-request-per-invoice fan-out with a single call

- Mobile bottom tab bar (pkg28): Home, Invoices, History, and Insights
  are now one thumb-tap away in a fixed bottom navigation bar with icons
  and labels, active-state highlighting, and iPhone safe-area padding.
  The fifth tab, Menu, opens the drawer, which on mobile now shows only
  Configure pages and the account row (the Work pages live in the tab
  bar). The redundant top-left hamburger is removed on mobile, and page
  content reserves space so the bar never covers it. Desktop navigation
  is unchanged

- Public demo access: the sign-in page can open an isolated viewer-only
  workspace without signup. The workspace is seeded idempotently with two
  clearly synthetic USD invoices successfully posted to QuickBooks and Zoho
  so Home, Invoices, History, Vendors, and Insights show a realistic processed
  workflow while all mutating invoice APIs remain forbidden to the demo user.

- Route-level loading screen (pkg27): navigating into /app (e.g. right
  after login) now shows an instant branded spinner ("Opening your
  workspace") instead of the old frozen-page feeling while the workspace
  renders

- Phase B AI routing (pkg25): in `auto` parser mode with a live AI
  provider configured, the deterministic parse runs first and external
  AI is invoked only when the supplier's format is in training or has
  never been seen — trusted formats parse with zero provider calls, and
  any reviewer correction demotes the format and re-opens AI routing.
  Auto-triggered runs are marked `AI/OCR TRIGGER: training_format` in
  the invoice document metadata. New repository lookup
  `get_supplier_format` backs the gate; three new tests cover
  unseen→AI, trusted→skip, demoted→AI-again, and explicit
  `parser_mode=ai` bypass (68 backend tests total)

- AI suggestions surfaced in review (pkg25): stored `AI/OCR SUGGESTIONS`
  now flow into the invoice review — a pinned "AI extraction ran" insight
  reports provider, model, and the training-format trigger, agreements
  annotate fields with "AI agrees", and disagreements raise the field to
  review severity showing the AI's value, confidence, and reason. AI
  values never enter the auto-apply suggested patch (review_only policy
  preserved). Two more tests cover end-to-end surfacing and the
  disagreement/no-patch-leak path (70 backend tests total)

- GitHub Actions workflow (Build Tally connector installer) that builds
  the Windows installer .exe on GitHub's Windows runners via PyInstaller
  and Inno Setup and publishes it as a downloadable artifact — no
  Windows machine needed; triggered manually from the Actions tab

### Fixed

- Demo data isolation now uses tenant IDs and membership ownership instead of
  organization display names. Any legacy shared demo membership is repaired
  automatically, only explicitly marked synthetic seed invoices are removed
  from the real workspace, browser preview invoices are organization-scoped,
  the sample-invoice action is visible only in the public demo account, and a
  conflict-safe display name supports databases with unique-name enforcement.
  Legacy duplicate memberships are collapsed to one isolated demo tenant
  without deleting legitimate invoices from any detached workspace. The
  cleanup wildcard is passed as a bound value for PostgreSQL/SQLite parity.

- Login feedback now appears on the first rendered frame after submission:
  the primary action holds focus, swaps to a stable "Signing in…" spinner,
  prevents duplicate authentication requests, announces progress to assistive
  technology, and returns to its ready state when authentication fails.

- Mobile workspace polish: invoice totals and statuses no longer clip in
  the demo queue, compact navigation tabs remain fully reachable without
  horizontal scrolling, settings navigation fits phone widths, summary
  metrics balance cleanly, and History activity metadata wraps without
  hiding invoice numbers or amounts.

- AI activation config: `SIFTENTRY_AI_MODEL` is now honored by the
  deployed configuration path (`AiExtractorConfig.from_settings`).
  Previously only local `from_environment` read it, so a hosted Groq
  deployment would silently send the default `gpt-4o-mini` model name
  and fail every call

### Changed

- History header polish (pkg27, supersedes pkg26): on mobile the
  audit-grade badge sits above the "Export audit log" button instead of
  colliding with it; the button now matches the Insights "Board pack"
  style — solid accent, content-width — on all screen sizes

- Sidebar account block redesign (pkg27): the card-in-card arrangement is
  replaced with a single row — avatar, name, role, and a compact labeled
  "Sign out" button with icon, visible resting border, and danger-tinted
  hover; the mobile drawer stacks a compact, identity-width button below
  the account details while desktop keeps the compact row

- Tally page download card now offers the Windows installer
  (SiftEntry-Tally-Connector-Setup-0.3.0.exe, one-click, no Python) as
  the primary download with the Python script kit as an IT-policy
  fallback; setup stepper wording updated to match

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
