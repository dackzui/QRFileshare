@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"
echo ========================================
echo  QRFileshare Installer Build
echo ========================================
echo.

REM --- Step 1: Python venv + dependencies ---
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating virtual environment...
  py -m venv .venv
  if errorlevel 1 (
    echo ERROR: Could not create venv. Install Python 3.11+ from python.org
    pause
    exit /b 1
  )
)

echo [1/3] Installing dependencies...
.venv\Scripts\pip install -r requirements.txt -q
if errorlevel 1 (
  echo ERROR: pip install failed.
  pause
  exit /b 1
)

if not exist "credentials.json" (
  echo.
  echo NOTE: credentials.json not found.
  echo       End users will need API setup unless you add it before building:
  echo       1. Copy credentials.json.example to credentials.json
  echo       2. Add your Google OAuth Web client from Google Cloud Console
  echo       3. Re-run this script
  echo.
) else (
  echo       Found credentials.json — will embed Google sign-in in the app.
)

echo [1/4] Syncing version files from version_info.py...
.venv\Scripts\python version_info.py --sync
if errorlevel 1 (
  echo ERROR: Could not sync version files.
  pause
  exit /b 1
)

REM --- Step 2: PyInstaller executable ---
echo [2/4] Building QRFileshare.exe...
.venv\Scripts\pyinstaller QRFileshare.spec --noconfirm --clean
if errorlevel 1 (
  echo ERROR: PyInstaller build failed.
  pause
  exit /b 1
)

if not exist "dist\QRFileshare.exe" (
  echo ERROR: dist\QRFileshare.exe was not created.
  pause
  exit /b 1
)

echo       Built: dist\QRFileshare.exe

REM --- Step 3: Inno Setup installer ---
set "ISCC="
if defined INNO_SETUP_DIR (
  set "ISCC=%INNO_SETUP_DIR%\ISCC.exe"
)
if not defined ISCC (
  if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
  )
)
if not defined ISCC (
  if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" (
    set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
  )
)
if not defined ISCC (
  where ISCC >nul 2>&1
  if not errorlevel 1 set "ISCC=ISCC"
)

if not defined ISCC (
  echo.
  echo [3/4] SKIPPED: Inno Setup not found.
  echo.
  echo The standalone exe is ready: dist\QRFileshare.exe
  echo.
  echo To create the Windows installer ^(.exe setup^):
  echo   1. Install Inno Setup 6 from https://jrsoftware.org/isinfo.php
  echo   2. Re-run this script, or run:
  echo      "C:\Program Files ^(x86^)\Inno Setup 6\ISCC.exe" installer\QRFileshare.iss
  echo.
  pause
  exit /b 0
)

echo [3/4] Building installer with Inno Setup...
"%ISCC%" installer\QRFileshare.iss
if errorlevel 1 (
  echo ERROR: Inno Setup build failed.
  pause
  exit /b 1
)

echo.
echo ========================================
echo  Build complete
echo ========================================
echo   App:       dist\QRFileshare.exe
echo   Installer: installer\Output\QRFileshare-Setup-1.2.0.exe
echo.
pause
