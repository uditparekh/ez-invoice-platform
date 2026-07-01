# SiftEntry Production Deployment Plan

This document describes the production target architecture. The current pilot
uses local SQLite, local document storage, and local Tally connectors. That is
right for demos, but production needs managed infrastructure and strict secret
boundaries.

## Target Architecture

- Next.js web app: Vercel, Render, Fly.io, AWS, or another managed web host.
- FastAPI backend: containerized service behind HTTPS.
- Deployable pilot database: SQLite on a persistent disk/volume.
- Production database: PostgreSQL with migrations, daily backups, and point-in-time restore.
- Storage: S3-compatible object storage for PDFs, extracted JSON, and posting evidence.
- Workers: a queue-backed worker pool for OCR, parsing, validation, posting, and retries.
- Secrets: managed secret storage for OAuth credentials, ERP tokens, connector tokens, and encryption keys.
- Tally connector: lightweight customer-side agent that posts to local TallyPrime on port `9000`.

## Environment Variables

Deployable pilot backend:

```bash
EZ_API_ENVIRONMENT=pilot
EZ_API_JWT_SECRET=replace-with-32-plus-random-bytes
EZ_API_DATABASE_URL=sqlite:////var/lib/siftentry/siftentry.db
EZ_API_UPLOAD_DIRECTORY=/var/lib/siftentry/uploads
EZ_STORAGE_BACKEND=s3
EZ_STORAGE_BUCKET=siftentry-documents
EZ_STORAGE_REGION=us-east-1
EZ_ENCRYPTION_KEY=replace-with-fernet-or-kms-backed-key
EZ_API_ALLOW_DEV_BOOTSTRAP=false
EZ_API_CORS_ORIGINS=https://app.siftentry.com
EZ_APP_BASE_URL=https://app.siftentry.com
EZ_API_PUBLIC_BASE_URL=https://api.siftentry.com
EZ_EMAIL_PROVIDER=smtp
EZ_EMAIL_FROM="SiftEntry <no-reply@siftentry.com>"
EZ_EMAIL_REPLY_TO=support@siftentry.com
EZ_SMTP_HOST=smtp.example.com
EZ_SMTP_PORT=587
EZ_SMTP_USERNAME=apikey-or-user
EZ_SMTP_PASSWORD=provider-secret
EZ_SMTP_USE_TLS=true
SIFTENTRY_AI_PROVIDER=profile_context
SIFTENTRY_AI_POLICY=review_only
# Later, when a live extraction service is selected:
# SIFTENTRY_AI_PROVIDER=webhook
# SIFTENTRY_AI_EXTRACTOR_URL=https://extractor.example.com/siftentry/extract
# SIFTENTRY_AI_EXTRACTOR_TOKEN=provider-or-internal-token
# SIFTENTRY_AI_TIMEOUT_SECONDS=8
# SIFTENTRY_AI_MAX_PAYLOAD_CHARS=120000
```

Future strict production, after the Postgres repository migration:

```bash
EZ_API_ENVIRONMENT=production
EZ_API_DATABASE_URL=postgresql://user:password@host:5432/siftentry
```

Web:

```bash
EZ_WEB_API_BASE_URL=https://api.siftentry.com
NEXT_PUBLIC_APP_NAME=SiftEntry
```

Accounting connectors:

```bash
QB_ENVIRONMENT=production
QB_REDIRECT_URI=https://api.siftentry.com/callback
ZOHO_REDIRECT_URI=https://api.siftentry.com/zoho/callback
```

Never store real client ERP credentials in Git, client profile exports, screenshots,
or demo ZIP files.

## Security Baseline

- Passwords are already hashed with Argon2.
- Access tokens are short-lived JWTs; refresh sessions are stored server-side and revocable.
- Browser sessions use HTTP-only cookies through the Next.js API boundary.
- Organization-scoped endpoints require membership checks.
- Client profiles should own posting settings and connector configuration.

Production additions still required:

- Password reset by email with one-time tokens.
- Invite email delivery rather than displaying dev invite tokens.
- Login throttling and account lockout after repeated failures.
- Role editing and member deactivation.
- Audit export for user, profile, invoice, and posting events.
- Encryption at rest for OAuth refresh tokens and connector secrets.
- Signed URLs for document download/preview.

## Deployment Readiness Check

After FastAPI starts, call:

```bash
curl https://api.siftentry.com/health/deployment
```

The endpoint returns non-secret checks for JWT configuration, CORS, email,
database mode, domain URLs, and AI/OCR extraction mode. Resolve every `problems`
item before a pilot client logs in. In strict production mode, the API fails at
startup if required controls are missing.

For authenticated product diagnostics, call:

```bash
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.siftentry.com/api/v1/system/ai-extraction
```

This returns non-secret provider state such as `profile_context_fallback` or
`external_webhook`, whether a token is configured, and the active review policy.

## Database Migration Path

The repository currently uses SQLite through `InvoiceRepository`. For production:

1. Add SQLAlchemy or SQLModel models that mirror the current repository schema.
2. Add Alembic migrations for users, memberships, organizations, profiles, invoices, corrections, and posting logs.
3. Keep repository methods as the application boundary while swapping storage implementation behind them.
4. Add migration tests that prove tenant isolation and posting-log history remain unchanged.
5. Run a one-time SQLite-to-Postgres importer only for real pilot data that should be preserved.

Until that migration lands, use `EZ_API_ENVIRONMENT=pilot` or `staging` with a
persistent SQLite volume. Do not run real production accounting data on an
ephemeral local database.

## Worker Queue Plan

Use a queue such as Redis Queue, Celery, Dramatiq, or cloud-native jobs.

Recommended jobs:

- `parse_invoice_pdf`
- `run_ocr_fallback`
- `validate_invoice`
- `post_to_accounting_system`
- `retry_failed_posting`
- `evaluate_parser_accuracy`
- `learn_vendor_correction`

Workers should write status, issues, request payloads, and response payloads to
posting logs so the UI always shows audit-ready evidence.

## Deployment Checklist

1. Provision PostgreSQL and object storage.
2. Configure secrets in the host provider.
3. Deploy FastAPI behind HTTPS.
4. Deploy Next.js with `EZ_WEB_API_BASE_URL` pointed at FastAPI.
5. Disable development bootstrap.
6. Create the first owner through a secure admin seed command.
7. Test login, invitation, upload, review, validation, and dry-run posting.
8. Pilot each accounting connector with one client profile before enabling live posting.
9. Enable backups, monitoring, and error alerts.
10. Document client-specific Tally connector setup for each pilot workspace.
