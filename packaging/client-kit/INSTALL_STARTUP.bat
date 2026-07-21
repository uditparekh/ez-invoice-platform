@echo off
setlocal
set TASK_NAME=SiftEntry Tally Connector
set RUNNER=%~dp0START_CONNECTOR.bat

echo Installing "%TASK_NAME%" so it opens when you sign in to Windows.
echo.

schtasks /Create /TN "%TASK_NAME%" /SC ONLOGON /TR "\"%RUNNER%\"" /F
if errorlevel 1 (
  echo.
  echo Could not create the startup task. Right-click this file and
  echo choose "Run as administrator", then try again.
  pause
  exit /b 1
)

echo.
echo Done. The connector will now start automatically when you sign in.
echo You can remove this later with UNINSTALL_STARTUP.bat.
pause
