@echo off
cd /d "%~dp0"
echo SiftEntry Tally Connector - one-time setup
echo.
echo Installing the small component the connector needs (requests)...
echo.
py -m pip install --upgrade requests
if errorlevel 1 (
  echo.
  echo py command failed. Trying python instead...
  python -m pip install --upgrade requests
  if errorlevel 1 (
    echo.
    echo Could not install. Is Python installed? See Step 1 in README-START-HERE.txt
  )
)
echo.
echo Setup finished. You can close this window.
pause
