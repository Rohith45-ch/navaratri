import os
import sqlite3
from pathlib import Path

# Base directory for the project
BASE_DIR = Path(__file__).resolve().parent

# Event Configuration
EVENT_NAME = os.getenv("EVENT_NAME", "College Annual Cultural Fest 2026")

# Public base URL of the verification server (default to http://localhost:8000/check/)
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000/check/")
if not BASE_URL.endswith("/"):
    BASE_URL += "/"

# SMTP Configuration
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "rohithkumar118a@gmail.com")
# Read sender password from environment variable; never hardcoded
SENDER_PASSWORD = os.getenv("SMTP_PASSWORD", os.getenv("SENDER_PASSWORD", ""))

# Database Configuration
DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "tickets.db")))

# QR Code storage directory
QR_DIR = BASE_DIR / "qr"


def init_db(conn: sqlite3.Connection) -> None:
    """Create the tickets table if it does not already exist."""
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                token TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                used INTEGER DEFAULT 0,
                used_at TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tickets_email ON tickets(email)")


def get_db(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Return a database connection with Row factory and ensure tables exist."""
    target_path = Path(db_path) if db_path else DB_PATH
    conn = sqlite3.connect(str(target_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn
