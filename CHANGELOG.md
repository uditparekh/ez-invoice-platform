# Changelog

All notable platform changes will be recorded here.

## [Unreleased]

### Added

- Next.js 16 customer application under `apps/web`
- Secure same-origin web API boundary with HTTP-only access and refresh cookies
- Login, logout, protected routes, and automatic FastAPI token rotation
- Organization-aware responsive application shell
- Functional invoice queue, status filtering, search, PDF upload, detail view,
  validation display, and line-item table
- Light and dark operational themes with mobile navigation

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
