import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Event settings
EVENT_NAME = os.getenv("EVENT_NAME", "NAITRA 26'")

# Public base URL of server (default: http://localhost:8000)
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")

# SMTP Configuration (default Gmail: smtp.gmail.com:465)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "")
# Read password from environment variable SMTP_PASSWORD - never hardcoded
SENDER_PASSWORD = os.getenv("SMTP_PASSWORD", "")

# Organizer authentication password from ORGANIZER_PASSWORD environment variable
ORGANIZER_PASSWORD = os.getenv("ORGANIZER_PASSWORD", "admin123")

# Flask secret key from FLASK_SECRET_KEY
SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "navaratri-event-passes-secret-key-2026")

# Database filename tickets.db
DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "tickets.db")))

# Google service account key path (default secrets/service_account.json)
SERVICE_ACCOUNT_KEY = Path(os.getenv("SERVICE_ACCOUNT_KEY", str(BASE_DIR / "secrets" / "service_account.json")))

# Google Sheet ID from SHEET_ID
SHEET_ID = os.getenv("SHEET_ID", "")

# QR code output folder
QR_DIR = BASE_DIR / "qr"
QR_DIR.mkdir(parents=True, exist_ok=True)

# Secrets directory (git-ignored)
(BASE_DIR / "secrets").mkdir(parents=True, exist_ok=True)
