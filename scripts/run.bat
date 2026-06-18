@echo off
REM ===== AdTrust CXAI - start the platform =====
if not exist .venv ( echo Run setup.bat first. & exit /b 1 )
call .venv\Scripts\activate.bat
echo [AdTrust CXAI] Starting on http://localhost:8000  (console at /, API docs at /docs)
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
