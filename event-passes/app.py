import csv
import io
import logging
import re
import secrets
import threading
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import config
import db
import mailer
import sheets_sync

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# ---------------------------------------------------------------
# In-memory store for pending CSV data (keyed by upload_id)
# and background job progress state
# ---------------------------------------------------------------
pending_uploads = {}  # upload_id -> list of {name, email}
progress_state = {
    "running": False,
    "sent": 0,
    "skipped": 0,
    "failed": 0,
    "total": 0,
}
progress_lock = threading.Lock()

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------
# HELPERS & AUTH
# ---------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            flash("Please log in with the organizer password.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.context_processor
def inject_globals():
    return {
        "config_event_name": config.EVENT_NAME,
        "last_sync_time": sheets_sync.get_last_sync_time(),
    }


# ---------------------------------------------------------------
# AUTH ROUTES
# ---------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        entered_password = request.form.get("password", "")
        if entered_password == config.ORGANIZER_PASSWORD:
            session.clear()
            session["logged_in"] = True
            flash("Welcome! Logged in as Event Organizer.", "success")
            return redirect(url_for("dashboard"))
        flash("Incorrect organizer password. Please try again.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# ---------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------

@app.route("/")
@app.route("/dashboard")
@login_required
def dashboard():
    stats = db.get_stats()
    attendees = db.get_all_tickets()
    last_sync = sheets_sync.get_last_sync_time()
    return render_template(
        "dashboard.html",
        stats=stats,
        attendees=attendees,
        last_sync_time=last_sync,
    )


@app.route("/download/not-entered")
@login_required
def download_not_entered():
    rows = db.get_not_entered()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["name", "email"])
    for r in rows:
        w.writerow([r["name"], r["email"]])
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=not_entered_attendees.csv"},
    )


@app.route("/sync", methods=["POST"])
@login_required
def sync_sheets():
    success = sheets_sync.sync_to_sheet()
    if success:
        flash("Google Sheet successfully synchronized!", "success")
    else:
        flash("Google Sheet sync failed. Check secrets/service_account.json and SHEET_ID.", "warning")
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------
# UPLOAD
# ---------------------------------------------------------------

@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        file = request.files.get("csv_file")
        if not file or not file.filename:
            flash("Please choose a CSV file to upload.", "danger")
            return redirect(url_for("upload"))

        try:
            content = file.stream.read().decode("utf-8-sig")
        except Exception as e:
            flash(f"Could not read CSV file: {e}", "danger")
            return redirect(url_for("upload"))

        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames:
            flash("The uploaded CSV file is empty.", "danger")
            return redirect(url_for("upload"))

        header_map = {col.strip().lower(): col for col in reader.fieldnames}
        name_key = header_map.get("name")
        email_key = header_map.get("email")

        if not name_key or not email_key:
            flash(
                f"CSV must contain 'name' and 'email' columns. Found: {list(reader.fieldnames)}",
                "danger",
            )
            return redirect(url_for("upload"))

        valid_rows = []
        invalid_count = 0
        for row in reader:
            n = (row.get(name_key) or "").strip()
            e = (row.get(email_key) or "").strip()
            if not n or not e or not EMAIL_REGEX.match(e):
                invalid_count += 1
                continue
            valid_rows.append({"name": n, "email": e})

        if not valid_rows:
            flash("No valid attendee rows were found in the file.", "danger")
            return redirect(url_for("upload"))

        upload_id = secrets.token_hex(16)
        pending_uploads[upload_id] = valid_rows
        session["upload_id"] = upload_id

        msg = f"Loaded {len(valid_rows)} valid attendee(s)."
        if invalid_count:
            msg += f" ({invalid_count} row(s) skipped due to missing name or bad email format)."
            flash(msg, "warning")
        else:
            flash(msg, "success")

        return render_template(
            "upload.html",
            preview_rows=valid_rows[:10],
            total_uploaded_rows=len(valid_rows),
            upload_ready=True,
        )

    return render_template("upload.html", preview_rows=None, upload_ready=False)


# ---------------------------------------------------------------
# PASS GENERATION & WORKER
# ---------------------------------------------------------------

def _worker_generate(attendees):
    global progress_state

    for item in attendees:
        name, email = item["name"], item["email"]

        # Skip existing emails
        if db.email_exists(email):
            with progress_lock:
                progress_state["skipped"] += 1
            continue

        token = secrets.token_urlsafe(24)
        try:
            db.insert_ticket(token, name, email)
            qr_path = mailer.generate_qr_image(token)
            mailer.send_pass_email(name, email, token, qr_path)
            db.set_email_status(token, "sent")
            with progress_lock:
                progress_state["sent"] += 1
        except Exception as exc:
            logger.error("Pass generation/send failed for %s: %s", email, exc)
            db.set_email_status(token, "failed")
            with progress_lock:
                progress_state["failed"] += 1

    with progress_lock:
        progress_state["running"] = False

    # Automatically sync to Google Sheet after bulk generation
    sheets_sync.sync_in_background()


@app.route("/generate-passes", methods=["POST"])
@login_required
def generate_passes():
    global progress_state

    upload_id = session.get("upload_id")
    attendees = pending_uploads.get(upload_id, []) if upload_id else []

    if not attendees:
        flash("No pending attendee list found. Please upload a CSV first.", "warning")
        return redirect(url_for("upload"))

    pending_uploads.pop(upload_id, None)
    session.pop("upload_id", None)

    with progress_lock:
        progress_state = {
            "running": True,
            "sent": 0,
            "skipped": 0,
            "failed": 0,
            "total": len(attendees),
        }

    t = threading.Thread(target=_worker_generate, args=(attendees,), daemon=True)
    t.start()
    return redirect(url_for("progress"))


@app.route("/progress")
@login_required
def progress():
    with progress_lock:
        snap = dict(progress_state)
    return render_template("progress.html", progress=snap)


@app.route("/progress/status")
@login_required
def progress_status():
    with progress_lock:
        return jsonify(progress_state)


# ---------------------------------------------------------------
# RESEND FAILED
# ---------------------------------------------------------------

def _worker_resend(failed_tickets):
    global progress_state

    for item in failed_tickets:
        token, name, email = item["token"], item["name"], item["email"]
        try:
            qr_path = config.QR_DIR / f"{token}.png"
            if not qr_path.exists():
                qr_path = mailer.generate_qr_image(token)
            mailer.send_pass_email(name, email, token, qr_path)
            db.set_email_status(token, "sent")
            with progress_lock:
                progress_state["sent"] += 1
        except Exception as exc:
            logger.error("Resend failed for %s: %s", email, exc)
            db.set_email_status(token, "failed")
            with progress_lock:
                progress_state["failed"] += 1

    with progress_lock:
        progress_state["running"] = False

    sheets_sync.sync_in_background()


@app.route("/resend-failed", methods=["POST"])
@login_required
def resend_failed():
    global progress_state
    failed_rows = db.get_failed_tickets()
    failed = [dict(r) for r in failed_rows]

    if not failed:
        flash("No failed emails to resend.", "info")
        return redirect(url_for("dashboard"))

    with progress_lock:
        progress_state = {
            "running": True,
            "sent": 0,
            "skipped": 0,
            "failed": 0,
            "total": len(failed),
        }

    t = threading.Thread(target=_worker_resend, args=(failed,), daemon=True)
    t.start()
    return redirect(url_for("progress"))


# ---------------------------------------------------------------
# GATE VERIFICATION (PUBLIC - NO LOGIN)
# ---------------------------------------------------------------

@app.route("/check/<token>", methods=["GET", "POST"])
def check_token(token: str):
    """
    Public gate verification endpoint.
    Sets used=1 and used_at=now if token exists and used=0.
    Returns:
      ALLOWED (200) on first scan
      ALREADY USED (409) if pass was previously verified
      INVALID (404) if token is unknown
    """
    changed, row = db.check_in(token)

    # Check if client expects JSON (e.g. from /scan fetch)
    accept_header = request.headers.get("Accept", "")
    wants_json = "application/json" in accept_header or request.args.get("format") == "json"

    if changed and row:
        sheets_sync.sync_in_background()
        name = row["name"]
        if wants_json:
            return jsonify({
                "status": "ALLOWED",
                "name": name,
                "message": "Entry granted. Welcome to the event!",
            }), 200
        return render_template(
            "verify.html",
            event_name=config.EVENT_NAME,
            status="ALLOWED",
            icon="✅",
            name=name,
            message="Entry granted. Welcome to the event!",
        ), 200

    if row:
        name = row["name"]
        used_at = row["used_at"] or "an earlier time"
        if wants_json:
            return jsonify({
                "status": "ALREADY USED",
                "name": name,
                "message": f"This pass was already used at {used_at}.",
            }), 409
        return render_template(
            "verify.html",
            event_name=config.EVENT_NAME,
            status="ALREADY USED",
            icon="⚠️",
            name=name,
            message=f"This pass was already used at {used_at}.",
        ), 409

    if wants_json:
        return jsonify({
            "status": "INVALID",
            "name": None,
            "message": "This ticket token is not found in the system.",
        }), 404

    return render_template(
        "verify.html",
        event_name=config.EVENT_NAME,
        status="INVALID",
        icon="❌",
        name=None,
        message="This ticket token is not found in the system.",
    ), 404


@app.route("/scan")
def scan_page():
    """Gate staff QR camera scanner interface."""
    return render_template("scan.html")


# ---------------------------------------------------------------
# APPLICATION ENTRYPOINT
# ---------------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
