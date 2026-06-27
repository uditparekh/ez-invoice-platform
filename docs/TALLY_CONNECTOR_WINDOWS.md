# SiftEntry Tally Connector for Windows

The hosted SiftEntry app cannot call a client's `localhost:9000`. In a browser
or cloud server, `localhost` means that same machine, not the accountant's
Windows computer. TallyPrime normally runs on the accountant's Windows computer,
so SiftEntry uses a small local connector that polls the cloud and posts into
local TallyPrime.

## Production Flow

1. The accountant opens TallyPrime and loads the correct company.
2. TallyPrime HTTP/XML access is enabled on port `9000`.
3. SiftEntry stores a client profile with exact Tally names: company, voucher
   type, purchase ledger, tax ledgers, stock item rules, TCS, round-off, and
   connector workspace/token.
4. The accountant reviews and approves invoices in SiftEntry.
5. The Windows connector polls SiftEntry for approved Tally jobs.
6. The connector posts each XML voucher to `http://localhost:9000`.
7. The connector returns the Tally result to SiftEntry for logs, retries, and
   invoice status.

## Client Setup

Install Python 3 on the Windows computer where TallyPrime is installed. During
installation, select:

```text
Add python.exe to PATH
```

Install packages from the `ez_invoice_app` folder:

```bat
py -m pip install --upgrade requests flask streamlit pandas pymupdf pypdf openpyxl pdfplumber
```

## Run the Status Window

Double-click:

```text
RUN_TALLY_CONNECTOR_STATUS_WINDOWS.bat
```

Fill in:

- SiftEntry URL: your deployed app URL, for example `https://app.siftentry.com`
- Workspace ID: the workspace ID shown in the SiftEntry client profile
- Connector token: the token shown in the SiftEntry client profile
- Tally URL: usually `http://localhost:9000`
- Poll seconds: `15`
- Claim limit: `5`

Click:

1. `Save settings`
2. `Test Tally`
3. `Poll once`
4. `Start connector`

The status window shows:

- Connected to SiftEntry
- Tally detected
- Last posted invoice
- Retry failed jobs

## Start Automatically On Login

After the connector works manually, double-click:

```text
INSTALL_TALLY_CONNECTOR_STARTUP_WINDOWS.bat
```

This creates a Windows startup task for the signed-in user. It is not a signed
enterprise Windows Service yet, but it gives pilot clients a reliable startup
experience without admin-heavy setup.

To remove it:

```text
UNINSTALL_TALLY_CONNECTOR_STARTUP_WINDOWS.bat
```

## Important Rules

- Do not expose Tally port `9000` to the internet.
- Keep TallyPrime open with the correct company loaded.
- Do not claim jobs if TallyPrime is offline. The connector checks Tally before
  polling SiftEntry.
- Store connector tokens like passwords. Rotate the token if a computer is
  replaced or an employee leaves.
