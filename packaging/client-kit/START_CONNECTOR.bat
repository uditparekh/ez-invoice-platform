@echo off
cd /d "%~dp0"
echo Starting the SiftEntry Tally Connector window...
py tally_connector_desktop.py
if errorlevel 1 (
  echo.
  echo py command failed. Trying python instead...
  python tally_connector_desktop.py
  if errorlevel 1 (
    echo.
    echo Could not start. Is Python installed? See Step 1 in README-START-HERE.txt
    pause
  )
)
