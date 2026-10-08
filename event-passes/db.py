import sqlite3
import logging
from datetime import datetime
from config import DB_PATH

logger = logging.getLogger(__name__)


def get_conn() -> sqlite3.Connection:
    """Return a sqlite3 connection with row_factory set to sqlite3.Row."""
    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the tickets table and indexes if they do not exist."""
    conn = get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                token TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                used INTEGER NOT NULL DEFAULT 0,
                used_at TEXT,
                email_status TEXT NOT NULL DEFAULT 'pending'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_email ON tickets (email)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_used ON tickets (used)")
        conn.commit()
        logger.info("Database initialized at %s", DB_PATH)
    finally:
        conn.close()


def insert_ticket(token: str, name: str, email: str) -> None:
    """Insert a new ticket row with email_status='pending'."""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO tickets (token, name, email, used, used_at, email_status) VALUES (?, ?, ?, 0, NULL, 'pending')",
            (token, name, email),
        )
        conn.commit()
    finally:
        conn.close()


def email_exists(email: str) -> bool:
    """Return True if a ticket with this email already exists."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM tickets WHERE email = ? LIMIT 1", (email,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def set_email_status(token: str, status: str) -> None:
    """Update the email_status column for the given token."""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE tickets SET email_status = ? WHERE token = ?",
            (status, token),
        )
        conn.commit()
    finally:
        conn.close()


def get_all_tickets():
    """Return all ticket rows ordered by insertion order (newest first)."""
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM tickets ORDER BY rowid DESC"
        ).fetchall()
    finally:
        conn.close()


def get_stats() -> dict:
    """Return aggregate statistics as a plain dict."""
    conn = get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        sent = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE email_status = 'sent'"
        ).fetchone()[0]
        failed = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE email_status = 'failed'"
        ).fetchone()[0]
        entered = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE used = 1"
        ).fetchone()[0]
        not_entered = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE used = 0"
        ).fetchone()[0]
        return {
            "total": total,
            "sent": sent,
            "failed": failed,
            "entered": entered,
            "not_entered": not_entered,
        }
    finally:
        conn.close()


def get_failed_tickets():
    """Return all ticket rows where email_status='failed'."""
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM tickets WHERE email_status = 'failed' ORDER BY rowid DESC"
        ).fetchall()
    finally:
        conn.close()


def get_not_entered():
    """Return all ticket rows where the attendee has not yet entered."""
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM tickets WHERE used = 0 ORDER BY name COLLATE NOCASE"
        ).fetchall()
    finally:
        conn.close()


def check_in(token: str):
    """
    Mark a ticket as used if it has not already been used.

    Returns:
        (changed: bool, row: sqlite3.Row | None)
        'changed' is True only when the UPDATE modified a row (used changed from 0 to 1).
        'row' is the ticket record (if found).
    """
    conn = get_conn()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor = conn.execute(
            "UPDATE tickets SET used = 1, used_at = ? WHERE token = ? AND used = 0",
            (now, token),
        )
        conn.commit()
        changed = cursor.rowcount > 0
        row = conn.execute(
            "SELECT name, used_at, used FROM tickets WHERE token = ?", (token,)
        ).fetchone()
        return changed, row
    finally:
        conn.close()


def get_ticket_by_token(token: str):
    """Return a single ticket row by token, or None if not found."""
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM tickets WHERE token = ?", (token,)
        ).fetchone()
    finally:
        conn.close()


# Automatically initialize the database on import
init_db()
