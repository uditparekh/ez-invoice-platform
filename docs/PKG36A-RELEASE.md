# pkg36A — read-only Tally master discovery

## Scope

Connector 0.6.0 adds **Sync Tally masters**, available while polling is stopped.
It authenticates a new sync session, exports the configured company identity and
five master collections, then uploads one complete snapshot. It does not claim
invoices, drain acknowledgements, read recovery files, import masters or post
vouchers. A zero-invoice workspace is sufficient. Restart polling separately.

Exports use fixed local XML collection definitions and an explicit
SVCURRENTCOMPANY. Names are XML-escaped, never interpolated as TDL. Company name
and nonempty GUID must agree before and after discovery. HTTP redirects, XML
entities/DTDs, malformed or unsuccessful responses, duplicate names, unexpected
object types, oversized data and partial exports fail closed. An empty master
collection is valid only with a successful Tally response. No balances, invoices,
bank details or voucher history are requested.

Protocol references: [Tally collection export examples](https://help.tallysolutions.com/sample-xml/)
and [company GUID documentation](https://help.tallysolutions.com/export-data-faq/).
These document the approach; they are not a substitute for testing a real Tally
installation. Supported limits: 4 MiB per XML response, 10,000 total master rows,
2 MiB serialized snapshot, 512 characters per master field. Exceeding a limit
produces a visible error; data is never silently truncated. Search suggestions
render at most 100 matching names; type more to narrow the full stored catalog.

## Storage and concurrency

The migration creates one `tally_master_sync` row per profile. A server-generated
ticket is bound to the profile revision, expires in ten minutes and is consumed
once. A later begin supersedes an older session. Begin/submit/confirmation use
the same database profile lock as configuration updates. No network calls run
inside database transactions. Failed exports/uploads preserve the last complete
snapshot and do not change the profile or its approved plans.

Snapshot access requires workspace membership. Uploads require the matching
connector workspace/token. Confirming mappings requires owner/admin/accountant;
viewers can inspect but cannot confirm. Tokens are not present in snapshots or
browser responses. Sync and confirmation emit audit events. The app gateway
explicitly permits only the two additional native POST paths, with its existing
body bound, no cookies, no redirect following and no arbitrary forwarding.

## What the labels mean

- **Found in Tally**: exact name present in the current company snapshot, less
  than 24 hours old. Not proof of accounting correctness or present-time existence.
- **Mapping confirmed**: an authorized accountant explicitly reviewed the saved
  rules against that snapshot. Confirmation is bound to snapshot ID and accounting
  configuration fingerprint; editing relevant rules or refreshing the snapshot
  requires confirmation again. It is never inferred from a dropdown selection.
- **Unverified**: no matching recent snapshot/name. Manual entry is retained for
  compatibility; saving or activating is not verification.

Checks include configured profile and item-rule ledger names, voucher type and
active inventory names. Hidden inventory settings do not block ledger-only
confirmation. Supplier ledgers derived from each invoice, unit compatibility,
tax correctness, quantities and invoice-specific allocations still require
posting-preview review. Company/source changes hide the old catalog. Successful
new sync resets prior mapping confirmation. Failed refreshes keep the last good
snapshot visibly dated; errors are shown in the connector.

## Rollout

1. Run Python tests, typecheck, lint, build and the full isolated browser suite.
2. Publish the release branch; pass SQLite/PostgreSQL CI and Windows tests.
3. The Windows build installs the packaged app and runs its isolated UI self-test
   at small work areas/high DPI, checks autostart and records source/hash metadata.
   It commits installer 0.6.0 and the matching kit to the release branch.
4. Confirm artifact, link and source versions agree, then fast-forward main.
   Never merge a link to an installer that has not been built successfully.
5. Verify main CI and deployments. Stop the old connector before upgrading;
   preserve settings and outbox/recovery files. Existing 0.5.0 posting remains
   compatible, but it cannot discover masters. No Railway variable is required.

## Physical Windows/Tally acceptance — still required

With an empty approved queue and a backup/test company, install/upgrade 0.6.0.
Test connection, stop polling, sync and compare exported names/GUID to Tally.
Test an empty godown collection, long/Unicode names, wrong company, Tally closed
mid-export and reopening a different company. Confirm failures preserve the last
good snapshot. Confirm ledger/item suggestions and accountant confirmation on
desktop/mobile. Check small-screen/high-DPI buttons and sign-in autostart.
Do not interpret a mock XML test or Windows CI as a real Tally acceptance pass.

## Deliberately unchanged

Approval remains mandatory. Frozen XML execution, uncertain-outcome holds and
the one-workspace-per-company guard are unchanged. Master snapshots do not
retroactively alter or verify an approved entry. This release is not a company
GUID-bound posting protocol or an exactly-once guarantee. **pkg36B reconciliation**
(durable voucher identity, scoped lookup and safe handling of inconclusive
results) is the next separate safety milestone. No automatic retries are enabled.
