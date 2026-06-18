@echo off
REM ===== AdTrust CXAI - Windows setup =====
echo [AdTrust CXAI] Creating virtual environment...
python -m venv .venv
if errorlevel 1 ( echo Python not found. Install Python 3.10+ and retry. & exit /b 1 )
call .venv\Scripts\activate.bat
echo [AdTrust CXAI] Installing dependencies...
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
echo.
echo [AdTrust CXAI] Setup complete. Run run.bat to start the platform.
