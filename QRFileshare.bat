@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Creating virtual environment...
  py -m venv .venv
  .venv\Scripts\pip install -r requirements.txt -q
)
start "" ".venv\Scripts\pythonw.exe" main.py
