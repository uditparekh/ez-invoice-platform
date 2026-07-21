SIFTENTRY TALLY CONNECTOR — SETUP GUIDE
========================================

This small program connects your TallyPrime to SiftEntry. When an invoice
is approved in SiftEntry, the connector enters it into Tally for you.

It runs quietly on this computer. It never opens Tally to the internet —
it only makes outgoing connections to SiftEntry, the same way a web
browser does.

You will need about 10 minutes, plus two values from the SiftEntry team:
  - Your Workspace ID
  - Your Connector Token

If you do not have these yet, ask your SiftEntry contact before starting.


STEP 1 — INSTALL PYTHON (one time only)
----------------------------------------
The connector runs on Python, a free program from python.org.

1. Open this address in your browser:  https://www.python.org/downloads/
2. Click the yellow "Download Python" button.
3. Run the downloaded file.
4. IMPORTANT: on the first screen, tick the box that says
   "Add python.exe to PATH", then click "Install Now".
5. Wait for it to finish and close the window.

If Python is already installed on this computer, skip this step.


STEP 2 — RUN SETUP (one time only)
-----------------------------------
In this folder, double-click:

    SETUP_WINDOWS.bat

A black window will appear and install one small component the
connector needs. When it says it is finished, press any key to close it.


STEP 3 — TURN ON TALLY'S CONNECTION
------------------------------------
1. Open TallyPrime.
2. Open the correct company.
3. Press F1 (Help), then go to:  Settings > Connectivity
4. Set "TallyPrime acting as" to "Both" (or "Server").
5. Set the Port to 9000.
6. Save and leave TallyPrime open.

You only need to do this once. "Enable ODBC" can stay off.


STEP 4 — START THE CONNECTOR AND ENTER YOUR DETAILS
----------------------------------------------------
In this folder, double-click:

    START_CONNECTOR.bat

The "SiftEntry Tally Connector" window will open. Fill in:

    SiftEntry URL:     https://app.siftentry.com
    Workspace ID:      (the value the SiftEntry team gave you)
    Connector token:   (the value the SiftEntry team gave you)
    Tally URL:         http://localhost:9000

Then click, in order:
    1. Save settings
    2. Test Tally      (should say Tally responded)
    3. Start connector

WHAT GOOD LOOKS LIKE: the window shows "Connected to SiftEntry" and
"Tally detected", and the SiftEntry website shows this connector as
Connected on the Tally integration page.


STEP 5 (OPTIONAL) — START AUTOMATICALLY WITH WINDOWS
-----------------------------------------------------
If you want the connector to open by itself every time you sign in
to Windows, double-click:

    INSTALL_STARTUP.bat

To undo this later, double-click UNINSTALL_STARTUP.bat.


DAY-TO-DAY USE
--------------
- Keep TallyPrime open with the correct company loaded.
- Keep the connector window open (you can minimize it).
- Approve invoices in SiftEntry as normal — the connector does the rest.


IF SOMETHING LOOKS WRONG
------------------------
"Tally not detected"
    TallyPrime is not open, the company is not loaded, or the port is
    not 9000. Repeat Step 3 and click "Test Tally" again.

"Cannot connect to SiftEntry" or "token" errors
    Check your internet connection, and check the Workspace ID and
    Connector token were typed exactly as given (no extra spaces).

"Ledger does not exist" or "Stock item does not exist"
    A name in SiftEntry does not exactly match the name in Tally.
    Tell your SiftEntry contact — this is fixed in SiftEntry, not here.

Anything else
    Take a photo or screenshot of the message and send it to your
    SiftEntry contact.


SAFETY NOTES
------------
- Never share your Connector Token except with the SiftEntry team.
- Never open port 9000 to the internet. The connector does not need it.
