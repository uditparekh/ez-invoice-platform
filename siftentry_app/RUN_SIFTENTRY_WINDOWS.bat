@echo off
cd /d "%~dp0"
echo Starting SiftEntry at http://127.0.0.1:8506
py -m streamlit run app.py --server.port 8506 --server.address 127.0.0.1
if errorlevel 1 (
  echo.
  echo py command failed. Trying python instead...
  python -m streamlit run app.py --server.port 8506 --server.address 127.0.0.1
)
pause
