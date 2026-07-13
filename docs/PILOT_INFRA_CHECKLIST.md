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

### 2b. Railway background worker (required)

Batch posting enqueues jobs into the `jobs` table; nothing runs them without a
worker. Create a **second Railway service from the same repository** in the
same project:

- New Service -> GitHub Repo -> select this repository again.
- In the service settings, set **Config file path** to `railway.worker.json`
  (it starts `python -m siftentry_app.backend.worker`, no health check,
  restart always).
- Attach the **same environment variables** as the API service (Railway
  shared variables make this one step).
- Optional: `SIFTENTRY_WORKER_POLL_SECONDS=2.0` (default).

Verify: enqueue a batch post from the app and confirm the job status moves
`queued -> running -> done` in the jobs view, and the worker logs show
`job <id> (batch_post_ready) claimed`.

### 2c. Railway spend limit (do this on day one)

Railway's compute spending limit is **opt-in and off by default** — overage
past the $20 Pro credit bills automatically. In Workspace Settings -> Usage,
set a hard compute limit (for example $50/month) and enable usage alert
emails. Two small always-on services (API + worker) typically land in the
$20-35/month range.

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

## 6. Email with Resend

### Outbound (invites, password resets) — needed at launch

Use Resend's **HTTPS API** provider, not SMTP: Railway restricts outbound
SMTP ports (blocked entirely on Free/Trial/Hobby, and intermittently
disrupted even on Pro), while HTTPS on port 443 always works. On the free
plan (3,000 emails/month, 100/day) create an API key, verify the sending
domain, then set on **Railway** (both services):

```bash
EZ_EMAIL_PROVIDER=resend
EZ_RESEND_API_KEY=<resend-api-key>
EZ_EMAIL_FROM=SiftEntry <no-reply@yourdomain.com>
EZ_APP_BASE_URL=https://app.yourdomain.com
```

`EZ_APP_BASE_URL` is required: password reset and invitation links are built
from it (without it they point at localhost).

Send yourself an invitation from the app to verify delivery before inviting a
pilot client.

### Inbound (email-in invoices) — optional, week two

The bridge route `apps/web/src/app/api/inbound/resend/route.ts` translates
Resend's `email.received` webhook into the backend's
`/api/v1/inbound/email` format. It stays inert (returns 503) until configured.

1. In Resend, set up receiving (default `.resend.app` address or a custom
   subdomain like `in.yourdomain.com`).
2. Create a webhook for the `email.received` event pointing at
   `https://<vercel-app-domain>/api/inbound/resend`; copy the signing secret.
3. Set on **Vercel**:

```bash
RESEND_WEBHOOK_SECRET=whsec_...
RESEND_API_KEY=re_...
SIFTENTRY_INBOUND_EMAIL_SECRET=<24+ char random secret>
SIFTENTRY_INBOUND_ORG_MAP={"invoices-clientA@in.yourdomain.com":"<org-id>"}
# or, single-tenant fallback:
# SIFTENTRY_INBOUND_DEFAULT_ORG=<org-id>
```

4. Set the same `SIFTENTRY_INBOUND_EMAIL_SECRET` on **Railway** (both
   services) so the backend accepts the bridge's calls.
5. Email a PDF to the intake address and confirm it appears in the invoice
   queue.

## 7. Monitoring

- Point a free uptime monitor (UptimeRobot, Better Stack, or similar) at
  `https://<railway-api-domain>/health` and the Vercel app URL, alerting to
  your phone/email.
- Supabase Pro includes daily backups with 7-day retention; confirm backups
  show in the dashboard after day one.
- Set billing/spend alerts on Vercel, Railway (section 2c), Supabase, and
  Resend.

## 8. Pre-launch QA

Before onboarding each client, run the end-to-end QA harness from the repo
root:

```bash
python tests/pilot_e2e_qa.py
```

It drives the full lifecycle (auth, profiles, upload, review corrections,
validate, approve, dry-run posting, batch worker jobs, connector
claim/results, inbound email, retention cleanup) against a throwaway
database — 42 checks, all must pass. Client profile onboarding note: for
Tally clients, `company_name` in the profile is REQUIRED (dry-run preflight
blocks without it), along with `purchase_ledger`, `tax_ledger`,
`round_off_ledger` (India GST), and `tax_mode`.

## 9. Signup order

Only Railway is subscribed so far. Recommended order:

1. **Domain** — everything below needs it (CORS origins, base URLs, email
   domain verification).
2. **Supabase Pro** — the backend cannot boot in pilot mode without the
   Postgres URL and storage bucket.
3. **Railway** — deploy API + worker services, set env vars and spend limit.
4. **Vercel Pro** — deploy the frontend, point `EZ_WEB_API_BASE_URL` at
   Railway.
5. **Resend Free** — outbound SMTP first; inbound bridge when ready.

Once both pilot clients have real data flowing and the config is stable,
switch `EZ_API_ENVIRONMENT` from `pilot` to `production` so the startup
readiness checks in `settings.py` (real JWT secret, no dev bootstrap, HTTPS
origins, SMTP configured, Postgres, hosted storage) actively block bad
config pushes.
