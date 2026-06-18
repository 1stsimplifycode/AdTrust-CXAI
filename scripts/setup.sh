#!/usr/bin/env bash
# AdTrust CXAI - macOS/Linux setup + run
set -e
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
echo "Setup complete. Starting on http://localhost:8000 ..."
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000
