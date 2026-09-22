# pkg36B — posting reconciliation / connector 0.7.0

## Contract

- Approval schema 2 freezes a stable per-organization/invoice UUID in REMOTEID
  and a narration marker, plus the company GUID from a matching master snapshot.
  The preview, immutable plan and executed XML remain identical. Supplier invoice
  numbers are not used as recovery identifiers.
- A new live claim requires the reconciliation protocol. Older connectors can
  still diagnose, heartbeat and acknowledge already-reserved jobs, but cannot
  claim new live work. One unresolved live claim per profile, enforced under the
  shared profile lock, blocks further work, even if a claim response was lost.
- Every returned reservation is journalled and fsynced before any Tally write.
  A single-use server execution permit pins the company identity; replay cannot
  authorize another import. The connector checks that identity locally before
  sending the frozen XML. Company/mapping changes do not rewrite in-flight work.
- Reconcile postings is an explicit read-only Tally operation. It finds cloud
  reservations even when the local claim response/journal was lost, and checks
  company identity before and after the bounded XML export. Only a unique exact
  reference with the approved marker and matching dates, party, ledgers, bill,
  inventory and batch allocations can succeed. Cancelled, optional, modified,
  oversized, malformed, unsupported, ambiguous and absent results remain held.
- Both connector and API compare evidence. The API stores the observed voucher,
  SHA-256, original company and external ID, and uses the existing atomic terminal
  transition for invoice/posting/audit. Replays cannot overwrite a winner. A lost
  reconciliation acknowledgement is recoverable without posting again.
- History distinguishes reconciliation from posting. Reserved attempts show
  stop/reconcile guidance; dead-end direct Tally retry buttons are removed.

## Deliberate limits

No automatic retry or automatic release follows absence. No rollback, voucher
mutation, multi-company routing or autoapproval was added. Legacy unresolved
postings without references/company identity and claims interrupted before an
execution permit require support review. A copied/restored Tally company can
share a GUID: do not operate multiple copies or use a backup as the live target.
Presence/equality is not a continuing guarantee against later edits in Tally.
Unsupported export shapes fail closed and need captured, redacted Tally fixtures
before support can extend matching. Cost-centre/bank allocation families are
not automatically reconciled.

## Rollout

Build and test 0.7.0 on the release branch. Publish the matching installer,
script kit, checksum manifest and download link together to main. Stop the old
connector before upgrading; retain settings and recovery files. Sync masters,
then revalidate/review/reapprove unclaimed older plans. Do not mutate existing
production invoices as a deployment check. The installer is unsigned.

## Acceptance and verification

Automated tests cover crash-before-result persistence, interrupted batches,
lost acknowledgements, profile isolation, single-use permits, company mismatch,
concurrent terminal outcomes, replay, empty/duplicate/modified vouchers, malformed
and oversized responses. Run SQLite and PostgreSQL suites, web typecheck/lint/
build/browser tests, and Windows installer/self-test before main publication.

**Physical Windows/Tally acceptance is separate and still required.** On an
isolated test company (not the live books), install/upgrade, test a zero-invoice
queue, sync company/masters, approve a sample, verify Day Book and Stock Summary,
then simulate a lost acknowledgement/interrupted result and verify recovery finds
exactly one voucher. Exercise wrong company, Tally closed, and edited voucher:
each must hold without importing. Confirm all actions/messages at the client's
DPI and sign-in autostart with an empty approved queue. CI's synthetic XML cannot
prove the real Tally version exposes every field required by the matcher.

## Primary protocol references

- [Tally XML examples](https://help.tallysolutions.com/sample-xml/): explicit
  company selection, export collections and voucher structures.
- [Import FAQ](https://help.tallysolutions.com/import-data-faq/): unique remote
  voucher IDs and overwrite/duplicate caveats. A repeated ID alone is not our
  safety mechanism.
- [Synchronization FAQ](https://help.tallysolutions.com/synchronisation-faq-tally/):
  company GUIDs, remote IDs and copied/split-company limitations.
