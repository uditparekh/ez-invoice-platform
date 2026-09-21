# pkg35A — Connector reliability, 0.5.0

## Pilot issues fixed

The Neel pilot reached Tally but failed cloud authentication. The app domain had
no native connector routes (404). Direct API calls exposed an unhandled
`hmac.compare_digest` TypeError for non-ASCII saved/supplied tokens (500).
The desktop Activity panel was below the usable screen area. None of these
requires uploading an invoice to test.

This release adds transport-safe token validation, secure token generation in
the existing profile editor, a four-route allowlisted web gateway, read-only
diagnostics, a persistent error strip and scrollable desktop body. Background
threads use immutable settings snapshots. Network/HTTP failures are actionable
and do not echo secrets. Ambiguous Tally outcomes pause for reconciliation.

## Deployment order

1. Verify source on `codex/pkg35a-connector-reliability` (SQLite/PostgreSQL,
   typecheck, lint, build, gateway/browser regressions).
2. Windows workflow builds 0.5.0, installs it in isolation, checks autostart and
   UI self-test, then commits the verified EXE/checksum/provenance and matching
   script kit to that branch. The source commit is recorded in the manifest.
3. Confirm the EXE exists before fast-forwarding main. The download card and
   binary must ship together. Preserve 0.4.0 for existing links/rollback.
4. Verify main matches remote, platform CI and deployments. Probe the public
   diagnostics endpoint without credentials: it must return JSON 401, not 404
   or a login redirect. Never probe production claim/results with client secrets.
5. Client upgrades while stopped, keeps URL/workspace/config/outbox, runs Test
   connection with no approved invoices, then performs supervised acceptance.

## Configuration

Vercel's existing `EZ_WEB_API_BASE_URL` is the only gateway upstream. The browser
session is not used or forwarded. Production fails closed if the URL is absent.
Do not add public tokens/environment secrets. Existing printable ASCII tokens
remain valid; rotate malformed tokens with the owner/admin's Generate button.

## Honest limits

- Diagnostics exports company names, not accounting masters or balances. Master
  readiness is explicitly Not verified; presence is not mapping correctness.
- Physical Windows/Tally acceptance is required. Synthetic fixtures and Windows
  installation tests cannot establish compatibility with the client's setup.
- Outcome-uncertain jobs remain reserved for manual investigation. No automated
  reconciliation or exactly-once guarantee is claimed.
- Profile reorganization, frozen approval plans, master sync, reconciliation,
  multi-company routing and learning changes are NOT included in 35A.
- Old onboarding PDFs are superseded by the versioned client guide in
  `packaging/windows/tally-connector/CLIENT_INSTALL_GUIDE.md`.

## References for the diagnostic export

Tally's Collection export envelope and native Name method:
https://help.tallysolutions.com/article/DeveloperReference/integration-capabilities/case_study_1.htm/
https://help.tallysolutions.com/sample-xml/

## Release verification record

- Source: `c1a092298edb93b6648a5e87c3018ce458884540`.
- Local: 163 Python tests passed; web typecheck, lint and production build passed;
  both native gateway Playwright regressions passed.
- [Platform verification](https://github.com/uditparekh/ez-invoice-platform/actions/runs/35643770236):
  web and both SQLite/PostgreSQL backend jobs passed.
- [Windows installer verification](https://github.com/uditparekh/ez-invoice-platform/actions/runs/35643770264):
  build, installation, packaged UI self-test and autostart registry checks passed.
- Installer: `SiftEntry-Tally-Connector-Setup-0.5.0.exe`, 13,085,646 bytes;
  SHA-256 `a08e3c97aed56dbf9b4ba6833041f88c4db194ae96a08867103f658bee5ae964`.
  Verified against the committed release manifest. Installer remains unsigned.
- Matching script kit contains the shared credentials helper and updated client
  guide. The 0.4.0 installer is preserved for existing links.
- Production deployment probes happen after publication; a green build alone
  does not establish that the live deployment is current.
- Physical Windows/Tally pilot acceptance remains pending until the client
  confirms it. In particular, verify the real company's diagnostic export,
  empty-workspace authentication, readable errors, and a Windows restart.
