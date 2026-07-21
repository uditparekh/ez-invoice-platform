@echo off
cd /d "%~dp0"
echo SiftEntry Tally Connector (cloud polling mode)
echo.
echo This connector polls SiftEntry for approved invoices and posts them
echo into the TallyPrime company open on this computer.
echo.
echo Before starting:
echo   1. Open TallyPrime and load the correct company.
echo   2. Confirm HTTP/XML access is enabled on port 9000.
echo   3. Save your workspace ID and connector token once using the
echo      SiftEntry Tally Connector status window (RUN_TALLY_CONNECTOR_STATUS_WINDOWS.bat),
echo      or set EZ_TALLY_CONNECTOR_TOKEN and EZ_WORKSPACE_ID before running this.
echo.
if "%SIFTENTRY_CLOUD_URL%"=="" set SIFTENTRY_CLOUD_URL=https://app.siftentry.com
py tally_connector_agent.py --poll-cloud --cloud-url %SIFTENTRY_CLOUD_URL%
if errorlevel 1 (
  echo.
  echo py command failed. Trying python instead...
  python tally_connector_agent.py --poll-cloud --cloud-url %SIFTENTRY_CLOUD_URL%
)
pause
