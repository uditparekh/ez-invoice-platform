@echo off
setlocal
set TASK_NAME=SiftEntry Tally Connector

echo Removing "%TASK_NAME%" startup task.
schtasks /Delete /TN "%TASK_NAME%" /F
if errorlevel 1 (
  echo.
  echo The startup task was not found or could not be removed.
  pause
  exit /b 1
)

echo.
echo Startup task removed.
pause
