# SiftEntry Tally Connector Windows Installer

This folder builds a one-click Windows installer for the local SiftEntry Tally
Connector.

The installed connector does not require Python on the accountant's computer.
It installs a packaged desktop app with:

- SiftEntry connection status
- TallyPrime detection
- last posted invoice
- failed-job count
- saved workspace/token/Tally URL settings
- optional auto-start when the Windows user signs in

## Build Requirements

Build this on Windows:

1. Python 3.11 or newer
2. Inno Setup 6
3. Internet access for Python build packages

Install Inno Setup from:

```text
https://jrsoftware.org/isdl.php
```

## Build Command

From the repository root:

```bat
packaging\windows\tally-connector\build_installer_windows.bat
```

The installer will be created at:

```text
packaging\windows\tally-connector\output\SiftEntry-Tally-Connector-Setup-0.2.0.exe
```

## Client Install Flow

Send the setup `.exe` to the client.

The client should:

1. Run the installer.
2. Keep `Start connector when I sign in` checked.
3. Launch `SiftEntry Tally Connector`.
4. Enter SiftEntry URL, workspace ID, connector token, and Tally URL.
5. Click `Save settings`.
6. Click `Test Tally`.
7. Click `Start connector`.

The Tally URL is usually:

```text
http://localhost:9000
```

The connector writes settings and status under the current Windows user's
AppData folder:

```text
%APPDATA%\SiftEntry\TallyConnector
```

## Production Notes

- Do not expose Tally port `9000` to the internet.
- The connector makes outbound HTTPS calls to SiftEntry.
- The connector checks TallyPrime before claiming jobs, so closed TallyPrime
  does not create false failed postings.
- For enterprise rollout, add code signing before distributing broadly.
