# SiftEntry Tally Connector: Client Install Guide

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

1. Run `SiftEntry-Tally-Connector-Setup-0.4.0.exe`.
2. Keep `Start connector when I sign in` selected.
3. Click `Install`.
4. Launch `SiftEntry Tally Connector` when setup finishes.

## Step 3: Connect It

In the connector window:

| Field | What to enter |
|---|---|
| SiftEntry URL | Your SiftEntry app URL |
| Workspace ID | The workspace ID from SiftEntry |
| Connector token | The token from SiftEntry |
| Tally URL | `http://localhost:9000` |

Then click:

1. `Save settings`
2. `Test Tally`
3. `Start connector`

## What Good Looks Like

The status window should show:

- `Connected to SiftEntry`
- `Tally detected`
- `Running`

When an invoice is approved in SiftEntry, the connector picks up the job, posts
it to TallyPrime, and records the result back to SiftEntry.

## Troubleshooting

| Message | What to check |
|---|---|
| Tally not detected | TallyPrime is open, company is loaded, port is `9000` |
| Cannot connect to SiftEntry | Internet connection, SiftEntry URL, workspace ID, token |
| Ledger does not exist | Exact Tally ledger name in the client profile |
| Stock item does not exist | Exact Tally stock item name in the client profile |

Never open port `9000` to the internet. The connector should run on the same
computer as TallyPrime and make outbound HTTPS calls to SiftEntry.
