@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Missing .venv. Run setup_workbuddy_bridge.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python tools\workbuddy-bridge\bridge.py watch
pause
