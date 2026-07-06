# SiftEntry Pilot Infra Checklist

Use this when creating the first hosted pilot environment.

## 1. Supabase

Create one Supabase project for the pilot.

Needed from Supabase:

- Project URL: `https://<project-ref>.supabase.co`
- Pooled Postgres connection string for Railway.
- Service-role key for backend-only storage access.

Create a private Storage bucket:

- Bucket name: `siftentry-pdf-review`
- Public bucket: off
- Purpose: temporary original PDFs during the review window only.

Do not put the service-role key in Vercel or browser code.

## 2. Railway

Deploy the FastAPI backend from the repository.

Recommended settings:

- Service root: repository root
- Install command: `pip install -r siftentry_app/requirements-api.txt`
- Start command: `python -m uvicorn siftentry_app.backend.main:app --host 0.0.0.0 --port $PORT`

Railway environment variables:

```bash
EZ_API_ENVIRONMENT=pilot
EZ_API_JWT_SECRET=<64-character-random-secret>
EZ_API_ALLOW_DEV_BOOTSTRAP=false
EZ_API_DATABASE_URL=<supabase-pooled-postgres-url>
EZ_STORAGE_BACKEND=supabase
EZ_SUPABASE_URL=https://<project-ref>.supabase.co
EZ_SUPABASE_SERVICE_ROLE_KEY=<supabase-service-role-key>
EZ_SUPABASE_STORAGE_BUCKET=siftentry-pdf-review
EZ_API_CORS_ORIGINS=https://<your-vercel-app-domain>
EZ_APP_BASE_URL=https://<your-vercel-app-domain>
EZ_API_PUBLIC_BASE_URL=https://<your-railway-api-domain>
EZ_EMAIL_PROVIDER=smtp
EZ_EMAIL_FROM=SiftEntry <no-reply@yourdomain.com>
EZ_SMTP_HOST=<smtp-host>
EZ_SMTP_PORT=587
EZ_SMTP_USERNAME=<smtp-username>
EZ_SMTP_PASSWORD=<smtp-password>
EZ_SMTP_USE_TLS=true
SIFTENTRY_AI_PROVIDER=profile_context
SIFTENTRY_AI_POLICY=review_only
SIFTENTRY_PDF_RETENTION_POLICY=review_window
SIFTENTRY_PDF_RETENTION_DAYS=3
```

After deploy, open:

- `https://<railway-api-domain>/health`
- `https://<railway-api-domain>/health/deployment`

Resolve every deployment problem before giving pilot access.

## 3. Vercel

Deploy the Next.js frontend from the same repository.

Recommended settings:

- Framework preset: Next.js
- Root directory: `apps/web`
- Install command: `pnpm install`
- Build command: `pnpm build`

Vercel environment variables:

```bash
NEXT_PUBLIC_APP_NAME=SiftEntry
EZ_WEB_API_BASE_URL=https://<railway-api-domain>
```

Do not add Supabase service-role keys, database URLs, SMTP passwords, QuickBooks
client secrets, or connector tokens to Vercel unless a variable is explicitly
frontend-safe.

## 4. Tally Pilot Flow

The cloud API cannot call a client laptop's `localhost:9000`. Tally clients use
the SiftEntry Tally Connector on the same Windows computer as TallyPrime.

Flow:

1. Client opens TallyPrime and enables HTTP/XML on port `9000`.
2. Client installs and starts the SiftEntry Tally Connector.
3. Connector polls Railway for approved jobs.
4. Connector posts XML to local TallyPrime.
5. Connector sends posting result and errors back to Railway.

## 5. Cost-Control Storage Policy

Default behavior:

- Original PDFs: private Supabase bucket, deleted after review window.
- Structured invoice JSON: kept in Postgres.
- File hash and metadata: kept in Postgres.
- Audit logs, corrections, and posting results: kept in Postgres.

Paid retention options later:

- 90-day PDF retention per client profile.
- Retain-until-deleted for regulated customers.
- Export-and-purge for customers who do not want document retention.
