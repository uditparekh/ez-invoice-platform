# Connector reliability and configuration contract

## Scope and sequence

This specification follows the September 2026 pilot findings. Release 35A fixes
connection reliability only. 35B reorganizes profile presentation without
changing posting semantics. 35C binds approval to a versioned posting plan and
adds preview/provenance. 36 adds read-only master sync and separately tested
reconciliation. Supplier-specific lessons/evaluation follow. Multi-company
routing, automatic approval and fine-tuning remain deferred.

One workspace per Tally company and explicit invoice approval remain mandatory.
No credential, invoice or client configuration is migrated automatically.

## 35A contracts

- Connector tokens are printable, non-space ASCII (1–512 characters for legacy
  compatibility). Generate 32 random bytes, displayed as 64 hexadecimal
  characters, for new credentials. Reject invalid new values on save; legacy
  malformed values and invalid authentication must never cause HTTP 500. Never
  log tokens, normalize internal characters, or echo credentials in errors.
- `https://app.siftentry.com` forwards ONLY the four explicit connector POST
  paths (diagnostics, heartbeat, claim, results). No browser login/session or
  redirect is involved. Forward connector authentication, never browser cookies.
  Use the existing server-only backend URL. Reject unsupported routes/methods,
  oversized requests, redirects and malformed upstream responses explicitly.
- Direct Railway base URLs remain supported. Never silently change a saved
  cloud URL: pending acknowledgements are bound to the original identity.
- Test connection is read-only: authenticates the profile and exports company
  names from local Tally; never claims, posts, or drains acknowledgements.
  Report cloud auth, Tally XML reachability, configured company availability,
  and master readiness independently. Master readiness stays **Not verified**
  until master sync; reachable does not mean verified or safe to post.
- Diagnostics cannot send cloud-provided XML to Tally. They build a fixed export
  locally. Authentication failure does not reveal other profiles or secrets.
- Desktop actions remain visible at small Windows work areas/high DPI; settings
  and activity scroll. Errors also appear in a persistent summary above content.
  Background workers receive immutable settings snapshots, never access Tk state,
  and surface exceptions. Editing settings requires stopping polling first.
- Existing outboxes are preserved. Lost acknowledgements retry acknowledgement
  only. Ambiguous Tally responses/timeouts are held for manual reconciliation,
  never submitted as retryable posting failures. Pending/uncertain work blocks
  new claims. Storage failures fail closed. Full voucher reconciliation is 36.

## Acceptance gates

1. Invalid supplied/stored tokens → 401; invalid new saved token → 422 without
   echoing the value. Existing ASCII credentials still work. Role checks hold.
2. Empty workspace: diagnostics succeeds on cloud auth and changes no invoices,
   posting attempts, or heartbeat records. Approved invoices remain unclaimed.
3. Tally down, wrong company, non-Tally HTTP 200, invalid XML, network failures
   and server errors are distinguishable. No pass is inferred from HTTP 200 alone.
4. Public proxy forwards only allowed calls and preserves 401/422/500 statuses;
   no credential forwarding across redirects or browser-cookie leakage.
5. Durable outbox regression suite passes including restart and identity mismatch;
   ambiguous results cannot automatically become a second voucher.
6. Backend suites (SQLite + PostgreSQL in CI), web typecheck/lint/build, proxy/UI
   regression tests, Windows packaging/self-test all pass before main publication.
7. Installer and fallback kit match source/version/checksums. Publish binary and
   download link together, never point production at a missing file.
8. Physical Windows/Tally acceptance: install/upgrade without losing settings,
   test an empty queue, wrong credential, Tally closed, correct/wrong company,
   high-DPI layout, sign-in autostart and a supervised approved test voucher.
   This is a human acceptance gate, not a claim that CI can validate real Tally.

## Later releases: non-negotiable interfaces

Saving a draft is not activation. Master presence is not accountant-confirmed
mapping. Profile defaults are not document evidence. Company selection must be
explicit. The approved posting plan must be what executes; relevant changes
require reapproval. An inconclusive reconciliation lookup never authorizes
reposting. Multi-company requires invoice destination binding and claim-time
enforcement, not merely relaxing the current profile guard.
