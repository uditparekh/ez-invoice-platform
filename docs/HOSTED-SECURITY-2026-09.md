# Hosted security hardening

This release addresses the September 24 authentication, document-storage and
connector-credential review. It is not a claim that the whole platform has passed
an independent penetration test. No production exploit tests were performed.

## Security contracts

- Recovery and invitation credentials are delivered through email only. Neither
  development nor hosted API responses contain usable recovery credentials.
  The web gateway also strips these fields during rolling deployments.
- Hosted startup validation applies to every environment except explicit
  `development` and `test`, including direct `create_app(settings)` construction.
  Use `EZ_API_ENVIRONMENT=production` in Railway API and worker. The historical
  `pilot` value now receives the same validation; it is not a bypass.
- JSON invoice import cannot attach a host filesystem path. Document download
  requires a server-created retained-file record. Local paths must resolve inside
  the configured root and the record's workspace directory; symlink escapes are
  rejected. Invoice clearing never follows untrusted legacy source paths.
- Login performs a password-hash verification for unknown users. Failed login
  budgets are ten attempts per email per minute (successful login clears the
  identity budget); reset requests are three per email per fifteen minutes;
  reset/invite confirmation is five attempts per token per minute; refresh is
  thirty per token per minute. A shared peer budget is 600 requests per minute
  across these routes. Responses use 429 with Retry-After.
- Counters use atomic database UPSERTs across API replicas, with hashed identifiers
  and expiry cleanup. Arbitrary forwarded IP headers are not trusted. The peer
  budget sees the web gateway as a peer: add a trusted edge/IP control before
  materially increasing public traffic, rather than trusting client headers.
- Reset consumption, password update and session revocation share one transaction.
  Concurrent use of one reset link has one winner. Password changes revoke existing
  access/refresh sessions; the UI returns to sign-in.
- Server-side connector tokens are stored as SHA-256 digests. Startup migrates
  old profile values without rotating the installed token or changing accounting
  plans. Hashes never work as bearer credentials and are redacted from responses.
  New generated tokens contain 32 random bytes. New manually supplied tokens must
  be at least 32 printable ASCII characters; prefer the generator.
- Connector identity and destination settings are Owner/Admin-only, including
  attempts to remove protected fields by omission. The legacy push adapter must
  not send stored credential digests to a user-configured destination. Hosted
  Tally posting continues through the Windows pull connector and frozen plans.
- API responses are no-store; both tiers set nosniff and referrer/frame policies.
  The web CSP restricts framing, object embedding and base URLs to the same origin.
  Same-origin objects are needed for native PDF previews served through the
  authenticated document route; external embedded objects remain blocked.
  This is deliberately
  not a full nonce-based script CSP. PDF responses have a fixed PDF MIME type;
  upload reads are bounded and main invoice uploads check the PDF signature.
- PDF parser versions are pinned. A full transitive dependency lock and ongoing
  vulnerability scanning remain separate supply-chain work.

## Deployment and recovery

1. Run the SQLite and PostgreSQL backend suites, typecheck, lint, build and browser
   regressions on the exact release commit. Deploy API, worker and web together.
2. The named migration `20260924_revoke_exposed_auth_links` expires outstanding
   password-reset and invitation links and revokes existing web sessions once.
   Users must sign in again; admins must resend pending invitations. Normal
   restarts do not revoke fresh sessions. No invoice, approval or posting is deleted.
3. Existing Windows connectors retain their configured token. No installer change
   is required. For rotation/reinstallation: stop the connector, generate a token
   in Client profiles → Connection, copy it before saving, save the profile and
   paste it into Windows. Resume and use the invoice-free connection diagnostics.
4. Do not roll back to a pre-hardening API: it cannot authenticate hashed connector
   credentials and would reintroduce the recovery-token exposure. Forward-fix.
5. Preserve provider/access logs. Review recovery requests, logins, imported paths
   and document access for the exposure period. This release does not establish
   whether unauthorized access occurred. Historical backups may still contain
   plaintext tokens; treat them as secrets and retain them securely.
6. Coordinate JWT-secret rotation on API and worker and rotate connector tokens
   with each client. The migration revokes old sessions, but does not change
   Railway secrets or the credential stored on a client's computer. If evidence
   suggests host-file exposure, investigate and rotate other accessible secrets
   as well (database, storage and email credentials), not only JWT.

## Regression evidence

`tests/test_hosted_security.py` covers hosted-mode rejection, email-only token
delivery, accountant file-read attempts, legacy deletion protection, symlink and
cross-workspace storage boundaries, MIME/size checks, concurrent multi-repository
rate limiting, unknown-user hash checks, reset races, one-time session/link
revocation, credential migration, generation and rotation. Existing approval,
connector outbox, master-sync and reconciliation tests remain release gates.

`apps/web/e2e/security-contracts.spec.ts` covers web response redaction, security
headers, demo credential denial and light/dark narrow-screen token setup.

## Remaining work is not hidden

- Independent security review and production log investigation are still required.
- Private invitation acceptance and refresh rotation retain their existing broader
  transaction design; this release's new single-winner guarantee is for password
  reset consumption, not a blanket concurrency claim for every auth operation.
- Email-provider timing can still differ between an existing and missing reset
  account; a durable outbound-email queue is the next architectural step.
- PDF extraction still runs in the request path. Worker isolation, parser resource
  limits, job leases and retries should be delivered as a focused reliability
  release. A bounded upload read is not a complete parser denial-of-service defense.
- The Windows connector needs its local bearer token to authenticate; this release
  hashes server storage, not the client's configuration file. Code signing and
  OS-protected client credential storage remain installer work.
- Legacy imports without retained file records no longer preview a PDF. Re-upload
  the original through the managed upload route; do not restore arbitrary paths.
- OCR, billing, accounting-target expansion and the broader business roadmap are
  outside this security release.
