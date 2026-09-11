# Connector 0.4.0 release and recovery

Pkg34 r2 is the baseline, with additional shipping hardening:

- Claiming an approved invoice and creating its posting record now commit in one transaction.
- Terminal posting, invoice status and audit events commit together. Concurrent conflict evidence is serialized.
- Live Tally posting through both the API and connector requires approval. A failed invoice must be reviewed and approved again before another live attempt.
- All profile response paths, including training samples, recommendations and activation, redact the token. Only owners/admins can change connector identity or reveal its token.
- Outbox entries are saved per voucher, flushed to disk, validated strictly and protected by a cross-process lock. Malformed/empty files stop processing without being discarded; incomplete cloud acknowledgements cannot erase the queue.
- Named configuration files have distinct outboxes. New results retain their workspace/cloud identity to prevent accidental acknowledgement under changed settings.
- The fallback script kit is regenerated from the same source as the installer.

## Release process

Build and verify on `codex/pkg34-complete` before updating main. The Windows workflow runs connector tests, builds and installs the installer, checks its autostart registry command, and starts the installed application's isolated UI self-test. This test makes no network or Tally calls. The workflow publishes the binary, SHA256SUMS.txt and connector-release.json to that release branch. Main is advanced only after checks and binary verification, avoiding a broken public download link.

Platform verification runs on pushes/PRs: backend tests with SQLite and PostgreSQL 17, and web typecheck/lint/build. Required branch protection is not automatically changed by this package.

The installer remains unsigned: no publisher signing certificate was supplied. Provenance/checksums establish which build was published, not a trusted Windows publisher identity.

## Before a client's first live post

1. Download 0.4.0, configure the exact workspace and Tally company, and confirm heartbeat.
2. Restart the real Windows PC and confirm Running without clicking Start.
3. Confirm Poll once refuses to overlap background polling.
4. Approve a disposable test invoice, check the voucher in Tally, then confirm the cloud result.
5. Exercise network loss and acknowledgement recovery before expanding use.

CI installation/UI checks do not validate an actual TallyPrime company, ledger mappings, stock allocations or a real Windows sign-in after reboot.

## Recovery rules

Never delete a pending/corrupt outbox to clear a warning. Preserve it, the connector logs and the posting IDs for support. A pending acknowledgement retries the result only; it must not resend the voucher.

An external Tally post and local disk persistence cannot be one atomic transaction. Process termination, disk failure, or a lost claim response can still leave an outcome unknown. Keep the invoice blocked and reconcile against the Tally Day Book/actual voucher before any retry. Do not automatically reset an uncertain `posting` invoice to approved. Reapproval authorizes a new attempt only after reconciliation.

The unique active-posting index is installed after legacy column migration. If an existing database already contains duplicate active attempts, index creation intentionally fails rather than silently altering accounting history; investigate/reconcile those attempts before deployment. No production data cleanup is performed automatically.

Analytics, event-backed History, invoice variance and broader design work from the QA report remain separate work. The History claim is corrected here, not its underlying event model.

References used for transaction/release design: [PostgreSQL row locking](https://www.postgresql.org/docs/17/explicit-locking.html), [GitHub branch-specific workflow runs](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-running-a-workflow).
