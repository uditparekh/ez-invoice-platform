# SiftEntry Tally Demo Checklist

Use this checklist on the Windows computer where TallyPrime is installed.
The production platform is https://app.siftentry.com — nothing else needs to
run locally except TallyPrime and the connector.

## 1. Start TallyPrime

1. Open TallyPrime.
2. Open the correct company.
3. Confirm HTTP/XML access is enabled on port `9000`
   (F1 Help -> Settings -> Connectivity, acting as `Both`, port `9000`).
4. Keep TallyPrime open during the demo.

Do not expose port `9000` to the internet. It is only used locally on the
Tally computer.

## 2. Start the connector

Use one of:

- The installed app: Start Menu -> `SiftEntry Tally Connector`
- The client kit: double-click `START_CONNECTOR.bat`
- This repo: double-click `RUN_TALLY_CONNECTOR_STATUS_WINDOWS.bat`

In the connector window confirm the saved settings:

- SiftEntry URL: `https://app.siftentry.com`
- Workspace ID and connector token: from the client profile's connection
  settings in SiftEntry
- Tally URL: `http://localhost:9000`

Click `Test Tally`, then `Start connector`.

## 3. Confirm the status in SiftEntry

1. Sign in at `https://app.siftentry.com`.
2. Open `Integrations -> Tally`.
3. The connector status card should show `Connected` and
   `TallyPrime: Detected` within about 15 seconds.

If it shows `Waiting for first check-in`, re-check the workspace ID and
token match the client profile exactly.

## 4. Run the demo flow

1. Upload or email in a sample invoice.
2. Review and approve it against the Tally client profile.
3. Watch the connector window post the voucher (about 15 seconds).
4. Show the voucher inside TallyPrime (Day Book).
5. Show the posting result and invoice timeline in SiftEntry.

## 5. If something fails

- `Tally not detected`: TallyPrime open? Company loaded? Port `9000`?
- `Connector workspace or token was not accepted`: values must match the
  client profile's connection settings exactly.
- `Ledger/stock item does not exist`: fix the exact names on the client
  profile in SiftEntry, then retry the posting.
