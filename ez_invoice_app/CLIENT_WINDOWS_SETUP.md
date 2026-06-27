# EZ-Invoice Windows Client Setup

This folder contains the EZ-Invoice local platform prototype.

## 1. Install Python

Install Python 3 from:

https://www.python.org/downloads/

Important: during installation, check:

```text
Add python.exe to PATH
```

After installation, open Command Prompt and verify:

```bat
py --version
```

If that does not work, try:

```bat
python --version
```

## 2. Install Required Packages

Open Command Prompt in this folder and run:

```bat
py -m pip install --upgrade streamlit pandas pymupdf pypdf openpyxl requests flask pdfplumber
```

If `py` does not work:

```bat
python -m pip install --upgrade streamlit pandas pymupdf pypdf openpyxl requests flask pdfplumber
```

## 3. Run EZ-Invoice

From this folder:

```bat
py -m streamlit run app.py --server.port 8506 --server.address 127.0.0.1
```

Then open this in the browser:

```text
http://127.0.0.1:8506
```

If port 8506 is busy, use 8507:

```bat
py -m streamlit run app.py --server.port 8507 --server.address 127.0.0.1
```

## 4. Optional: Connect To TallyPrime

Use this only on the computer where TallyPrime is installed and open.

1. Open TallyPrime.
2. Open the correct company.
3. Enable HTTP/XML access on port 9000.
4. Keep TallyPrime open.
5. Open a second Command Prompt in this folder.
6. Run:

```bat
set EZ_TALLY_CONNECTOR_TOKEN=replace-with-a-local-token
py tally_connector_agent.py --workspace-id local-workspace --tally-url http://localhost:9000
```

The connector should show:

```text
Running on http://127.0.0.1:8765
```

Leave that window open.

## 5. Configure Tally In EZ-Invoice

Inside EZ-Invoice:

1. Go to Tally.
2. In Client Workspace, enter the client company name and legal aliases, then click Save Client Workspace.
3. In Local Connector, use:

```text
Connector URL: http://127.0.0.1:8765
Workspace ID: local-workspace
Connector token: replace-with-a-local-token
```

4. Click Save Connector.
5. Click Test Connector.
6. In Tally Voucher Settings, enter the Tally company name and click Save Tally Settings.
7. Click Test Tally via Connector or Test Tally Port.

If the test succeeds, invoice vouchers can be posted to Tally after review.

## Notes

- Do not expose Tally port 9000 to the internet.
- Review invoice totals, tax totals, vendor names, and line items before posting.
- This package is a local prototype. Production deployment should use a secured cloud app plus a packaged local Tally connector.
