@echo off
echo Installing EZ-Invoice Python packages...
py -m pip install --upgrade streamlit pandas pymupdf pypdf openpyxl requests flask pdfplumber
if errorlevel 1 (
  echo.
  echo py command failed. Trying python instead...
  python -m pip install --upgrade streamlit pandas pymupdf pypdf openpyxl requests flask pdfplumber
)
echo.
echo Done. If there were no errors, run RUN_EZ_INVOICE_WINDOWS.bat next.
pause
