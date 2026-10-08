import logging
import threading
from datetime import datetime

import config
import db

logger = logging.getLogger(__name__)

_last_sync_time: str | None = None
_sync_lock = threading.Lock()


def get_last_sync_time() -> str | None:
    """Return the timestamp of the last successful Google Sheet sync, or None."""
    return _last_sync_time


def sync_to_sheet() -> bool:
    """
    Synchronise all ticket data from SQLite to the configured Google Sheet.
    SQLite is the source of truth.
    Overwrites the first worksheet with header:
    name, email, token, email_status, used, used_at

    Returns True on success, False on failure.
    Logs error and never raises exceptions.
    """
    global _last_sync_time

    if not config.SERVICE_ACCOUNT_KEY.exists():
        logger.warning(
            "Service account key file not found at %s. Google Sheet sync skipped.",
            config.SERVICE_ACCOUNT_KEY,
        )
        return False

    if not config.SHEET_ID:
        logger.warning("SHEET_ID environment variable not set. Google Sheet sync skipped.")
        return False

    with _sync_lock:
        try:
            import gspread
            from google.oauth2.service_account import Credentials

            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_file(
                str(config.SERVICE_ACCOUNT_KEY), scopes=scopes
            )
            gc = gspread.authorize(creds)
            sh = gc.open_by_key(config.SHEET_ID)
            ws = sh.sheet1

            header = ["name", "email", "token", "email_status", "used", "used_at"]
            rows = [header]

            for ticket in db.get_all_tickets():
                rows.append([
                    ticket["name"],
                    ticket["email"],
                    ticket["token"],
                    ticket["email_status"],
                    ticket["used"],
                    ticket["used_at"] or "",
                ])

            ws.clear()
            ws.update(rows, "A1")

            _last_sync_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info("Google Sheet synced successfully at %s (%d rows)", _last_sync_time, len(rows) - 1)
            return True

        except Exception as exc:
            logger.error("Failed to sync SQLite to Google Sheet: %s", exc)
            return False


def sync_in_background() -> None:
    """Run sync_to_sheet() in a background daemon thread so caller never waits."""
    t = threading.Thread(target=sync_to_sheet, daemon=True, name="SheetSyncWorker")
    t.start()
