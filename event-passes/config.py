import os
import sqlite3
from pathlib import Path

# Base project directory
BASE_DIR = Path(__file__).resolve().parent

# Event settings
EVENT_NAME = os.getenv("EVENT_NAME", "College Annual Cultural Fest 2026")

# Public base URL of server (default: http://localhost:8000)
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")

# SMTP Configuration (default Gmail: smtp.gmail.com:465)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "rohithkumar118a@gmail.com")
# Read password from environment variable - never hardcoded
SENDER_PASSWORD = os.getenv("SMTP_PASSWORD", os.getenv("SENDER_PASSWORD", ""))

# Database settings
DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "tickets.db")))

# Organizer authentication password from environment
ORGANIZER_PASSWORD = os.getenv("ORGANIZER_PASSWORD", "admin123")

# Flask session secret key
SECRET_KEY = os.getenv("SECRET_KEY", "navaratri-event-passes-secret-key-2026")

# QR code output folder
QR_DIR = BASE_DIR / "qr"
QR_DIR.mkdir(parents=True, exist_ok=True)


def init_db(conn: sqlite3.Connection) -> None:
    """Create tickets table if not exists with all required columns."""
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                token TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                used INTEGER DEFAULT 0,
                used_at TEXT,
                email_status TEXT DEFAULT 'pending'
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tickets_email ON tickets(email)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tickets_used ON tickets(used)")


def get_db(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Get SQLite connection with Row factory and initialize tables."""
    target_path = Path(db_path) if db_path else DB_PATH
    conn = sqlite3.connect(str(target_path), timeout=20.0)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn
