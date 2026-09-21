# pkg35C — Tally posting previews and frozen approval plans

## Contract

The proposed entry is decoded from the exact Tally XML built for that invoice
and selected profile. It displays company, voucher number/type/date, currency,
ledger debits/credits, stock quantities, rates, allocations and godowns. Expand
Exact Tally XML to inspect the complete payload. Preview performs no network call,
claim or posting. Existing profile preflight checks and an entry balance check
block incomplete plans. Foreign-currency conversion is not supported: invoice
currency must equal the profile currency, which the accountant must confirm is
the Tally company's base currency.

Approval requires the preview hash the user reviewed. The API rebuilds and checks
it inside a database transaction, then saves an append-only versioned plan with
approver, timestamp, input fingerprints and XML. A stale preview returns HTTP 409.
No connector credentials are stored in a plan or returned by the preview endpoint.

Connector claims atomically validate the current invoice, approved destination
and profile fingerprint, claim the invoice, and copy the stored plan into the
posting attempt. Jobs carry the saved XML; they never regenerate it from current
settings. Connector 0.5.0 already consumes this contract; no installer change is
needed. All live hosted Tally posting uses that durable queue, not the older web
direct-post route. Manual result imports cannot bypass the approved Tally job.

## Change and concurrency rules

- Relevant profile changes return pending approved invoices to Validated and
  record an approval-invalidated event. Descriptions, token rotation, training
  guidance and other non-accounting fields do not invalidate the entry.
- Invoice corrections return it to Extracted. Save, validate, preview and approve
  again. The previous plan remains available as historical evidence.
- Profile changes and claims share a database row lock. Invoice approval/claim
  and correction/validation use revision compare-and-set checks. No process-local
  lock is relied on for correctness. SQLite and PostgreSQL are both release gates.
- Already-claimed entries cannot be recalled by editing a profile. They execute
  their original plan. Posting/posted invoices cannot be edited or revalidated.
- Failed entries require validation and a new approval. Uncertain outcomes remain
  held by pkg35A; this release does not add automatic retry or reconciliation.
- Pre-release Approved invoices without a plan are not claimed. They must be
  validated and approved again through the preview. No production invoices are
  automatically reapproved, migrated to a destination, or posted during rollout.

## Review UI and provenance

Desktop Review and mobile Approvals share the preview, explicit review checkbox,
loading/error states, and frozen version display. Unsaved review edits block
approval. Light/dark layouts are tested at 1440, 390 and 320px, including large
amounts and long accounting names. The approvals headline and ledger amounts
must not clip; narrow screens stack the ledger name and amount.

New parsed invoices record field origins. Profile-filled currency and line
defaults are distinguished from extraction; saved reviewer changes are marked
Reviewer confirmed even when learning is opted out. AI suggestions remain
display-only and never enter the one-click suggested patch. Legacy records with
no provenance explicitly say Origin not recorded. The aggregate line-items card
says Includes profile defaults when any line received profile-filled values;
this is not a per-cell provenance timeline or a claim of model accuracy.

## Boundaries

Frozen execution applies to **Tally only**. Other destinations retain their
existing workflow and are not presented as frozen/exact-entry previews. One
workspace per Tally company remains the supported pilot setup. Master sync,
verified dropdowns, durable voucher reconciliation and extraction-learning
evaluation remain later packages. This is not an exactly-once guarantee across
the Tally call and local outbox disk write, nor proof of master existence.

## Release gates

Full backend suite, SQLite/PostgreSQL CI, typecheck, lint, production build,
six preview/approval browser scenarios plus the existing reporting/profile/gateway
regressions. Tests cover exact XML, stale inputs, immutable versions, concurrent
approvals and edits/claims, transaction rollback, secret-free viewer previews,
credential rotation, field origins, currency mismatches and bypass prevention.
Browser tests run only against isolated localhost services. Physical Windows /
Tally acceptance remains a client-side check before live accounting use.

Local release verification: 190 backend tests passed (five existing SWIG
deprecation warnings), 23 browser tests passed, and typecheck/lint/build passed.
Light desktop and dark 320px screenshots were visually inspected; the mobile
ledger layout and headline amount were corrected and re-tested. GitHub database
matrix and deployment results are verified separately before the release handoff.
