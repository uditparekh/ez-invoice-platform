# Zoho Books Sandbox Setup

## 1. Create the API client

1. Sign in to the Zoho API Console for the same Zoho data center as the Books organization.
2. Create a server-based application.
3. Add `http://localhost:8001/zoho/callback` as an authorized redirect URI.
4. Keep the Client ID and Client Secret private.

## 2. Start SiftEntry on macOS

```bash
cd "/PATH/TO/siftentry_app"

export ZOHO_CLIENT_ID="YOUR_ZOHO_CLIENT_ID"
export ZOHO_CLIENT_SECRET="YOUR_ZOHO_CLIENT_SECRET"
export ZOHO_REDIRECT_URI="http://localhost:8001/zoho/callback"
export ZOHO_ACCOUNTS_BASE_URL="https://accounts.zoho.in"
export ZOHO_API_BASE_URL="https://www.zohoapis.in/books/v3"
export ZOHO_USE_LOCAL_CALLBACK="true"

python3 -m streamlit run app.py --server.port 8506
```

## 3. Connect and configure

1. Open `http://127.0.0.1:8506`.
2. Select **Zoho Books** in the sidebar.
3. Click **Connect Zoho Books** and approve access.
4. Select the client organization.
5. Refresh the Chart of Accounts.
6. Map materials, services, freight, fees, taxes, and general expenses.
7. Select a default purchase tax only when the uploaded invoices contain tax.

## 4. Post a test Bill

1. Upload and process a supplier invoice.
2. Review the supplier, invoice number, dates, line items, currency, and total.
3. Select **Zoho Books** as the primary target.
4. Click **Send to Zoho Books**.
5. Confirm the returned Bill ID, then verify the Bill inside Zoho Books.

Do not post the same supplier invoice twice. SiftEntry also keeps a local
supplier-plus-invoice duplicate record for the selected organization.
