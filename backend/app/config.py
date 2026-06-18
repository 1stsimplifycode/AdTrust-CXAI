"""Configuration via environment variables (12-factor)."""
from __future__ import annotations

import os


class Settings:
    APP_NAME = "AdTrust CXAI"
    VERSION = "1.0.0"
    # auto-seed synthetic population on startup (set 0 to disable)
    SEED_ON_START = os.getenv("SEED_ON_START", "1") == "1"
    # CORS origins (comma separated). "*" by default for demo.
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
    PORT = int(os.getenv("PORT", "8000"))


settings = Settings()
