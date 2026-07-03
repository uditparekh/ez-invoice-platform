@echo off
setlocal
cd /d "%~dp0"
echo Starting SiftEntry Tally Connector status window...
echo.
py tally_connector_desktop.py
if errorlevel 1 (
  echo.
  echo py command failed. Trying python instead...
  python tally_connector_desktop.py
)
pause
