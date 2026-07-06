# SiftEntry Roadmap Status

This is the commit checklist for the current platform state. Keep this file as
the practical product-tracking view; keep `PROJECT_MAP.md` as the repository map.

## Completed Foundation

- Streamlit demo preserved for client demos.
- Next.js product shell with login, invoices, history, analytics, settings, integrations, profile management, and review flows.
- FastAPI backend with auth, organizations, memberships, invoices, profiles, posting logs, retry hooks, storage settings, and same-origin API support.
- PDF retention infrastructure with invoice file metadata, SHA-256 hashes, review-window retention, paid 90-day retention policy support, and cleanup endpoint.
- Hosted pilot infrastructure scaffolding for Supabase Postgres, private Supabase PDF storage, Railway backend deployment, and Vercel frontend deployment.
- Repository hygiene pass with clear file ownership rules, ignored runtime artifacts, one root project map, and a docs index for tracking.
- QuickBooks, Tally, and Zoho integration foundations.
- Tally local connector foundation with desktop status window and Windows packaging path.
- Tally connector installer packaging v1 with Windows build workflow and client install guide.
- Inbound invoice email webhook with shared-secret security, email metadata, and profile-aware PDF retention.
- Mobile approval view at `/app/approvals` for phone-sized invoice sign-off.
- Client profiles with accounting-system setup, country/currency/tax detection, training samples, generated recommendations, admin review, and activation.
- Invoice Review Workspace v1 with PDF preview, editable extraction fields, line-item review, parser evaluation hooks, and saved correction signals.
- Tally hardening v1 for accounting voucher and item invoice modes, GST/IGST/CGST/SGST, TCS, round-off, godown, stock item, HSN, and UOM fields.

## In Progress

- External AI/OCR extraction provider integration.
- Vendor-specific learning from saved corrections.
- Batch parser evaluation dashboard.
- More live Tally item-invoice testing with real client edge cases.
- Live staging deployment with account-created Supabase/Railway/Vercel projects, real email secrets, lifecycle cleanup scheduling, and worker queues.
- Code signing and managed release distribution for the Windows connector.

## Controlled Commit Checklist

Before committing:

1. Confirm generated caches and local databases are ignored.
2. Confirm new files follow `PROJECT_MAP.md` ownership rules.
3. Run the Python test suite.
4. Run the Next.js production build.
5. Review `git status --short` for only source, docs, and tests.
6. Commit with a message that reflects the milestone, not every tiny UI iteration.

Suggested commit message:

```text
Productize onboarding profiles and Tally posting
```

## Next Product Milestones

1. Run one clean local demo: login, upload invoice, review extraction, save corrections, activate a client profile, and post/export through the selected accounting target.
2. Wire a real OCR/LLM provider and worker queue for difficult invoices.
3. Convert correction history into automatic vendor/profile parser learning.
4. Harden Tally with more real invoices and better error explanations.
5. Create Supabase/Railway/Vercel accounts, deploy staging with the pilot checklist, schedule retention cleanup, and verify HTTPS/email/secrets.
6. Code-sign the Windows Tally connector before broad customer rollout.
