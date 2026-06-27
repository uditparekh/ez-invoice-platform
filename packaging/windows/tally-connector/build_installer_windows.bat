@echo off
setlocal

set SCRIPT_DIR=%~dp0
set ROOT_DIR=%SCRIPT_DIR%..\..\..
set DIST_DIR=%SCRIPT_DIR%dist
set BUILD_DIR=%SCRIPT_DIR%build
set OUTPUT_DIR=%SCRIPT_DIR%output
set SPEC_FILE=%SCRIPT_DIR%SiftEntryTallyConnector.spec
set ISS_FILE=%SCRIPT_DIR%SiftEntryTallyConnector.iss

echo.
echo Building SiftEntry Tally Connector installer
echo Root: %ROOT_DIR%
echo.

pushd "%ROOT_DIR%" || exit /b 1

echo Installing build requirements...
py -m pip install --upgrade -r "packaging\windows\tally-connector\requirements.txt"
if errorlevel 1 (
  echo Failed to install build requirements.
  popd
  exit /b 1
)

echo.
echo Building Windows app with PyInstaller...
py -m PyInstaller --noconfirm --clean --distpath "%DIST_DIR%" --workpath "%BUILD_DIR%" "%SPEC_FILE%"
if errorlevel 1 (
  echo PyInstaller build failed.
  popd
  exit /b 1
)

popd

set ISCC_EXE=
where ISCC.exe >nul 2>nul
if not errorlevel 1 set ISCC_EXE=ISCC.exe

if "%ISCC_EXE%"=="" if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC_EXE=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if "%ISCC_EXE%"=="" if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set ISCC_EXE=%ProgramFiles%\Inno Setup 6\ISCC.exe

if "%ISCC_EXE%"=="" (
  echo.
  echo Inno Setup 6 was not found.
  echo Install it from https://jrsoftware.org/isdl.php and run this build again.
  exit /b 1
)

echo.
echo Building one-click installer with Inno Setup...
pushd "%SCRIPT_DIR%" || exit /b 1
"%ISCC_EXE%" "%ISS_FILE%"
if errorlevel 1 (
  echo Inno Setup build failed.
  popd
  exit /b 1
)
popd

echo.
echo Installer ready:
dir /b "%OUTPUT_DIR%\SiftEntry-Tally-Connector-Setup-*.exe"
echo.
exit /b 0
