# Changelog

All notable platform changes will be recorded here.

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
