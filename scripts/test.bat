@echo off
REM ===== AdTrust CXAI - smoke test the API =====
if not exist .venv ( echo Run setup.bat first. & exit /b 1 )
call .venv\Scripts\activate.bat
echo [AdTrust CXAI] Running smoke tests...
python scripts\smoke_test.py
