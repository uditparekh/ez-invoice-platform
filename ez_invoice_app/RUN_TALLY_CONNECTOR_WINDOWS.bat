@echo off
cd /d "%~dp0"
set EZ_TALLY_CONNECTOR_TOKEN=replace-with-a-local-token
echo Starting EZ-Invoice Tally Connector at http://127.0.0.1:8765
echo Make sure TallyPrime is open and HTTP/XML port 9000 is enabled.
py tally_connector_agent.py --workspace-id local-workspace --tally-url http://localhost:9000
if errorlevel 1 (
  echo.
  echo py command failed. Trying python instead...
  python tally_connector_agent.py --workspace-id local-workspace --tally-url http://localhost:9000
)
pause
