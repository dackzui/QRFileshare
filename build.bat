@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pyinstaller.exe" (
  py -m venv .venv
  .venv\Scripts\pip install -r requirements.txt -q
)
.venv\Scripts\python version_info.py --sync
.venv\Scripts\pyinstaller QRFileshare.spec --noconfirm --clean
echo.
echo Built: dist\QRFileshare.exe
echo For full installer, run: build_installer.bat
pause
