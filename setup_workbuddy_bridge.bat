@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3.11 -m venv .venv
  if errorlevel 1 goto :error
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 goto :error
python -m pip install -r tools\workbuddy-bridge\requirements.txt
if errorlevel 1 goto :error
python tools\workbuddy-bridge\bridge.py init
if errorlevel 1 goto :error
python tools\workbuddy-bridge\bridge.py setup
if errorlevel 1 goto :error
python tools\workbuddy-bridge\bridge.py auth
if errorlevel 1 goto :error
python tools\workbuddy-bridge\bridge.py status
if errorlevel 1 goto :error
echo.
echo Setup finished. Review the bridge README before enabling continuous watch mode.
pause
exit /b 0
:error
echo.
echo Setup did not finish. Read the error above; do not paste secret values into chat.
pause
exit /b 1
