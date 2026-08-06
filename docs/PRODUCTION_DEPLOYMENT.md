# SiftEntry Production Deployment Plan

This document describes the hosted pilot and production target architecture.
Local SQLite and local PDF storage remain useful for development, but pilot
clients should run on managed Postgres, private object storage, and strict
secret boundaries.

## Target Architecture

- Next.js web app: Vercel.
- FastAPI backend: Railway service behind HTTPS.
- Pilot database: Supabase Postgres with backups enabled.
- Storage: Supabase private bucket for retained PDFs during the review window.
- Workers: a queue-backed worker pool for OCR, parsing, validation, posting, and retries.
- Secrets: managed secret storage for OAuth credentials, ERP tokens, connector tokens, and encryption keys.
- Tally connector: lightweight customer-side agent that posts to local TallyPrime on port `9000`.

## Environment Variables

Railway backend:

```bash
EZ_API_ENVIRONMENT=pilot
EZ_API_JWT_SECRET=replace-with-32-plus-random-bytes
EZ_API_DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres
EZ_STORAGE_BACKEND=supabase
EZ_SUPABASE_URL=https://<project-ref>.supabase.co
EZ_SUPABASE_SERVICE_ROLE_KEY=replace-with-supabase-service-role-key
EZ_SUPABASE_STORAGE_BUCKET=siftentry-pdf-review
SIFTENTRY_PDF_RETENTION_POLICY=review_window
SIFTENTRY_PDF_RETENTION_DAYS=3
EZ_API_ALLOW_DEV_BOOTSTRAP=false
EZ_API_CORS_ORIGINS=https://app.siftentry.com
EZ_APP_BASE_URL=https://app.siftentry.com
EZ_API_PUBLIC_BASE_URL=https://siftentry-api-production.up.railway.app
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

Vercel frontend:

```bash
EZ_WEB_API_BASE_URL=https://siftentry-api-production.up.railway.app
NEXT_PUBLIC_APP_NAME=SiftEntry
```

Accounting connectors:

```bash
QB_ENVIRONMENT=production
QB_REDIRECT_URI=https://app.siftentry.com/callback
ZOHO_REDIRECT_URI=https://app.siftentry.com/zoho/callback
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

- Login throttling and account lockout after repeated failures.
- Role editing and member deactivation.
- Audit export for user, profile, invoice, and posting events.
- Encryption at rest for OAuth refresh tokens and connector secrets.
- Signed URLs can be added later; today the authenticated API streams retained
  private documents from Supabase Storage.

## Deployment Readiness Check

After FastAPI starts, call:

```bash
curl https://siftentry-api-production.up.railway.app/health/deployment
```

The endpoint returns non-secret checks for JWT configuration, CORS, email,
database mode, domain URLs, and AI/OCR extraction mode. Resolve every `problems`
item before a pilot client logs in. In strict production mode, the API fails at
startup if required controls are missing.

For authenticated product diagnostics, call:

```bash
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://siftentry-api-production.up.railway.app/api/v1/system/ai-extraction
```

This returns non-secret provider state such as `profile_context_fallback` or
`external_webhook`, whether a token is configured, and the active review policy.

## Pilot Storage Policy

Store only what matters by default:

- Keep structured invoice JSON, extracted fields, review corrections, hashes,
  audit logs, profile mappings, and posting results in Supabase Postgres.
- Keep original PDFs in the private Supabase bucket only for the review window.
- Default review window: `SIFTENTRY_PDF_RETENTION_DAYS=3`.
- Auto-delete expired PDF objects through `/api/v1/organizations/{id}/storage/cleanup`
  or a scheduled Railway job.
- Offer paid long-term retention later by switching a client profile to
  `extended_90_days` or `retain_until_deleted`.

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

1. Create a Supabase project and private bucket `siftentry-pdf-review`.
2. Configure backend secrets in Railway, including Supabase database/storage values.
3. Deploy FastAPI behind HTTPS on Railway.
4. Deploy Next.js on Vercel with `EZ_WEB_API_BASE_URL` pointed at Railway.
5. Disable development bootstrap.
6. Create the first owner through a secure admin seed command.
7. Test login, invitation, upload, review, validation, and dry-run posting.
8. Pilot each accounting connector with one client profile before enabling live posting.
9. Enable backups, monitoring, and error alerts.
10. Document client-specific Tally connector setup for each pilot workspace.
