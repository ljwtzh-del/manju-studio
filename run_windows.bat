@echo off
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  py -3.11 -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -r requirements.txt
if not exist .env copy .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8600 --reload
