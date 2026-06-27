@echo off
setlocal
set TASK_NAME=SiftEntry Tally Connector
set RUNNER=%~dp0RUN_TALLY_CONNECTOR_STATUS_WINDOWS.bat

echo Installing "%TASK_NAME%" as a Windows startup task.
echo This opens the SiftEntry Tally Connector status window when this Windows user signs in.
echo.

schtasks /Create /TN "%TASK_NAME%" /SC ONLOGON /TR "\"%RUNNER%\"" /F
if errorlevel 1 (
  echo.
  echo Could not create the startup task. Try running this file as Administrator.
  pause
  exit /b 1
)

echo.
echo Startup task installed.
echo You can remove it later with UNINSTALL_TALLY_CONNECTOR_STARTUP_WINDOWS.bat.
pause
