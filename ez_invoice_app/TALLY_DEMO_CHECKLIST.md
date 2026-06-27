# EZ-Invoice Tally Demo Checklist

Use this checklist on the Windows computer where TallyPrime is installed.

## 1. Start TallyPrime

1. Open TallyPrime.
2. Open the correct company.
3. Confirm HTTP/XML access is enabled on port `9000`.
4. Keep TallyPrime open during the demo.

Do not expose port `9000` to the internet. It should only be used locally on the Tally computer.

## 2. Start EZ-Invoice

In the `ez_invoice_app` folder, double-click:

```text
RUN_EZ_INVOICE_WINDOWS.bat
```

Open this URL in Chrome or Edge:

```text
http://127.0.0.1:8506
```

## 3. Start The Tally Connector

Open a second Command Prompt in the same folder, or double-click:

```text
RUN_TALLY_CONNECTOR_WINDOWS.bat
```

The connector should show:

```text
Running on http://127.0.0.1:8765
```

Leave this connector window open.

## 4. Configure EZ-Invoice Tally Page

In EZ-Invoice, open `Tally`.

Use these connector values:

```text
Connector URL: http://127.0.0.1:8765
Workspace ID: local-workspace
Connector token: replace-with-a-local-token
```

Click:

1. `Save Connector`
2. `Test Connector`
3. `Test Tally via Connector`

Then fill `Tally Voucher Settings`:

```text
Client setup profile: choose Generic / manual setup or India GST item invoice template
Tally URL: http://localhost:9000
Tally company name: exact company name open in TallyPrime
Posting mode: Item Invoice for stock-item purchase bills; Accounting Voucher for non-stock bills
Voucher type: Purchase
Purchase/expense ledger: ledger that exists in TallyPrime
GST ledger: exact GST ledger from the client company
Stock item override: optional exact Tally stock item name
Stock item HSN: optional HSN that should map to the stock item override
Tally stock UOM: exact unit symbol in Tally, for example KGS
TCS ledger: optional exact ledger, for example TCS
Round-off ledger: optional exact ledger, for example ROUND OFF
Godown/location master name: optional, leave blank if Tally does not require a godown
```

Click `Save Tally Settings`.

## 5. Process Invoices

1. Open `Invoices`.
2. Click `Upload PDFs`.
3. Select invoice PDFs.
4. Click `Process PDFs`.
5. Review invoice number, vendor, date, total, and line items.
6. Open `Tally`.
7. Select only reviewed invoices in the Tally Posting Queue.
8. Click `Post Selected to Tally`.

If posting fails, check the error message first. Most Tally failures are caused by a missing vendor ledger, missing purchase ledger, wrong company name, or TallyPrime not being open.
