# Changelog

All notable platform changes will be recorded here.

## [Unreleased]

### Fixed

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
