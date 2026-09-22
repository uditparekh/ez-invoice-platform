# SiftEntry Tally Connector 0.7.0: Client Install Guide

This connector lets SiftEntry post approved invoices into the TallyPrime company
running on the same Windows computer. It does not expose TallyPrime to the
internet.

## Before You Start

You need:

- A Windows computer with TallyPrime installed.
- The correct TallyPrime company opened.
- The SiftEntry connector setup file.
- Your SiftEntry workspace ID and connector token.

## Step 1: Enable TallyPrime XML Access

1. Open TallyPrime.
2. Open the correct company.
3. Go to `F1: Help` → `Settings` → `Connectivity`.
4. Set `TallyPrime acting as` to `Server` or `Both`.
5. Set `Port` to `9000`.
6. Save the settings.

`Enable ODBC` can remain `No`. SiftEntry uses Tally XML over HTTP, not ODBC.

## Step 2: Install the Connector

1. Download `SiftEntry-Tally-Connector-Setup-0.7.0.exe` from your SiftEntry Integrations → Tally page. The installer includes Python; no separate Python installation is needed.
2. Keep `Start connector when I sign in` selected.
3. Click `Install`.
4. Launch `SiftEntry Tally Connector` when setup finishes.

## Step 3: Connect It

In the connector window:

| Field | What to enter |
|---|---|
| SiftEntry URL | `https://app.siftentry.com` — no `/app` suffix |
| Workspace ID | The workspace ID from SiftEntry |
| Connector token | Owner/admin: Generate secure token in the client profile, Save profile, then copy that same token here |
| Tally URL | `http://localhost:9000` |

Then click:

1. `Save settings`
2. `Test connection` — safe with zero invoices; it never claims or posts anything.
3. Check cloud authentication, Tally XML reachability, and the configured company.
4. While stopped, click `Sync Tally masters`. This only reads company identity,
   ledger names, stock items, units, godowns and voucher types. It never claims
   or posts invoices and does not touch recovery files. Keep the company open
   until the completion message appears. It may take a few minutes.
5. In SiftEntry → Client profiles → Posting rules, click `Refresh snapshot`.
   Check the company name/GUID and last successful sync. Search the exact names
   in the fields, save, and have your accountant explicitly confirm the saved
   mappings. **Found in Tally** is not proof that a ledger is the right one.
   Supplier ledgers and invoice-specific allocations still need invoice review.
6. `Start connector` only after setup is confirmed and you are ready for approved
   invoices to post. `Poll once` is a posting action, not a connection test.

If upgrading an existing connection using the Railway URL, keep that URL until
pending results are reconciled. Both the app base URL and
`https://siftentry-api-production.up.railway.app` are supported. Never change the
URL/workspace or delete recovery files to clear a warning. Stop the old connector
before upgrading; the installer preserves saved settings and recovery files.

## What Good Looks Like

The status window should show:

- Cloud: `Connected` (authentication passed).
- Tally: `Online` (XML export responded).
- Company: the company configured in your profile is available in Tally.
- Masters: a recent snapshot after sync. Snapshots older than 24 hours need
  another sync before confirming mappings; a failure preserves the last good
  snapshot. This is a read-only snapshot, not continuous synchronization.
- `Running` only after Start connector. The website status updates during normal
  polling; Test connection alone deliberately does not change its heartbeat.

When an invoice is approved in SiftEntry, the connector picks up the job, posts
it to TallyPrime, and records the result back to SiftEntry.

## Troubleshooting

| Message | What to check |
|---|---|
| Tally not detected | TallyPrime is open, company is loaded, port is `9000` |
| Cannot connect to SiftEntry | Internet connection, SiftEntry URL, workspace ID, token |
| HTTP 401 | Owner/admin should check the saved Workspace ID/token. Use Generate secure token if the token contains special pasted characters, save the profile, and update the stopped connector. Never send tokens in support messages. |
| HTTP 404 | Use the exact base URL without `/app`. Contact support if it persists. |
| HTTP 500/502/503 | Server/gateway failure. Send the visible message and time to support; do not change Tally settings. |
| Company not found | Open the intended Tally company and check its exact name in the client profile. |
| Outcome uncertain | Stop, then select Reconcile postings. It only looks up existing vouchers. If the lookup is inconclusive, keep the hold and contact support. Never re-enter the voucher or delete recovery files. |
| Ledger does not exist | Exact Tally ledger name in the client profile |
| Stock item does not exist | Exact Tally stock item name in the client profile |

Never open port `9000` to the internet. The connector should run on the same
computer as TallyPrime and make outbound HTTPS calls to SiftEntry.

The message strip and action buttons remain visible; settings and Activity can
scroll on smaller screens. Keep tokens hidden when sending a screenshot.
An HTTP response timeout does not prove Tally rejected a voucher. An inconclusive
lookup must never trigger a blind repost.

## First supervised acceptance

### Recovering an interrupted posting

1. Stop the connector and leave the original Tally company open.
2. Select **Reconcile postings**. The connector checks the company GUID and
   searches the durable reference frozen into the approved entry. It does not
   import, alter, delete or retry a voucher.
3. Only one non-cancelled, non-optional voucher with matching accounting and
   inventory allocations can be acknowledged as posted. History records the
   reconciliation separately from a normal posting.
4. A missing voucher, duplicate match, edited entry, changed company, unsupported
   export, or connection error stays on hold. **Not found does not mean safe to
   retry.** Contact support with the visible message and posting reference, not
   credentials. Older postings without a pinned company/reference also need
   manual review. A claim interrupted before its single-use execution permit
   was issued remains held; this release deliberately does not release it.
5. Restart polling only when recovery has completed or support has resolved the
   hold. Ordinary cloud acknowledgements continue to retry without reposting.

New approvals freeze the company GUID as well as the accounting entry. Sync
masters before approval. A changed company identity or a pre-0.7 approval plan
requires validating, reviewing and approving again; existing in-flight plans
are never rewritten. Master mapping freshness is still a separate 24-hour
check: the execution guard compares the live company identity before posting.

### Client acceptance checklist

Test with no invoices first. Confirm a wrong token gives an actionable error,
then restore the correct token. Close Tally and verify its check fails independently
of cloud authentication. Open the correct company and repeat Test connection.
Only then review/validate/approve one agreed sample and reconcile it in Tally.
Test Windows sign-in autostart with an empty approved queue. Real Windows/Tally
acceptance must be performed at the client; a packaging smoke test is not a
substitute. The installer is unsigned: follow the client's IT policy, never
disable antivirus or bypass warnings without verifying the download.
