import csv
import io
import json
import re
import secrets
import threading
from datetime import datetime
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

from config import (
    EVENT_NAME,
    ORGANIZER_PASSWORD,
    QR_DIR,
    SECRET_KEY,
    get_db,
)
import mailer

app = Flask(__name__)
app.secret_key = SECRET_KEY

# ---------------------------------------------------------------
# In-memory store for pending CSV data (keyed by random upload_id)
# and background job progress.
# ---------------------------------------------------------------
pending_uploads = {}   # upload_id -> list of {name, email}
progress_state = {
    "running": False,
    "sent": 0,
    "skipped": 0,
    "failed": 0,
    "total": 0,
}
progress_lock = threading.Lock()


# ---------------------------------------------------------------
# HELPERS
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
    return {"config_event_name": EVENT_NAME}


EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        if request.form.get("password", "") == ORGANIZER_PASSWORD:
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
    conn = get_db()
    cur = conn.cursor()
    total        = cur.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    sent_emails  = cur.execute("SELECT COUNT(*) FROM tickets WHERE email_status='sent'").fetchone()[0]
    failed_emails= cur.execute("SELECT COUNT(*) FROM tickets WHERE email_status='failed'").fetchone()[0]
    entered      = cur.execute("SELECT COUNT(*) FROM tickets WHERE used=1").fetchone()[0]
    not_entered  = cur.execute("SELECT COUNT(*) FROM tickets WHERE used=0").fetchone()[0]
    attendees    = cur.execute("SELECT * FROM tickets ORDER BY rowid DESC").fetchall()
    conn.close()

    stats = dict(
        total=total,
        sent_emails=sent_emails,
        failed_emails=failed_emails,
        entered=entered,
        not_entered=not_entered,
    )
    return render_template("dashboard.html", stats=stats, attendees=attendees)


@app.route("/download/not-entered")
@login_required
def download_not_entered():
    conn = get_db()
    rows = conn.execute(
        "SELECT name, email FROM tickets WHERE used=0 ORDER BY name COLLATE NOCASE"
    ).fetchall()
    conn.close()

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


# ---------------------------------------------------------------
# UPLOAD (Step 1 – preview only, no generation yet)
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
            flash(f"Could not read file: {e}", "danger")
            return redirect(url_for("upload"))

        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames:
            flash("The uploaded CSV file is empty.", "danger")
            return redirect(url_for("upload"))

        header_map = {col.strip().lower(): col for col in reader.fieldnames}
        name_key  = header_map.get("name")
        email_key = header_map.get("email")
        if not name_key or not email_key:
            flash(
                f"CSV must contain 'name' and 'email' columns. "
                f"Found: {list(reader.fieldnames)}",
                "danger",
            )
            return redirect(url_for("upload"))

        valid_rows, invalid_count = [], 0
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

        # Store full data in server memory keyed by a random upload ID,
        # keep the ID in the session (safe – no large data in cookie).
        upload_id = secrets.token_hex(16)
        pending_uploads[upload_id] = valid_rows
        session["upload_id"] = upload_id

        msg = f"Loaded {len(valid_rows)} valid attendee(s)."
        if invalid_count:
            msg += f" {invalid_count} row(s) skipped (missing name / bad email)."
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
# GENERATE PASSES (Step 2 – triggered from upload preview page)
# ---------------------------------------------------------------

def _worker_generate(attendees):
    global progress_state
    conn = get_db()
    cur  = conn.cursor()

    for item in attendees:
        name, email = item["name"], item["email"]

        # Skip duplicates
        if cur.execute("SELECT 1 FROM tickets WHERE email=?", (email,)).fetchone():
            with progress_lock:
                progress_state["skipped"] += 1
            continue

        token = secrets.token_urlsafe(24)
        try:
            cur.execute(
                "INSERT INTO tickets (token,name,email,used,used_at,email_status) "
                "VALUES (?,?,?,0,NULL,'pending')",
                (token, name, email),
            )
            conn.commit()

            qr_path = mailer.generate_qr_image(token)
            mailer.send_pass_email(name, email, token, qr_path)

            cur.execute("UPDATE tickets SET email_status='sent' WHERE token=?", (token,))
            conn.commit()
            with progress_lock:
                progress_state["sent"] += 1

        except Exception as exc:
            print(f"[MAILER ERROR] {email}: {exc}")
            try:
                cur.execute(
                    "UPDATE tickets SET email_status='failed' WHERE token=?", (token,)
                )
                conn.commit()
            except Exception:
                pass
            with progress_lock:
                progress_state["failed"] += 1

    conn.close()
    with progress_lock:
        progress_state["running"] = False


@app.route("/generate-passes", methods=["POST"])
@login_required
def generate_passes():
    global progress_state

    upload_id = session.get("upload_id")
    attendees = pending_uploads.get(upload_id, []) if upload_id else []

    if not attendees:
        flash("No pending attendee list found. Please upload a CSV first.", "warning")
        return redirect(url_for("upload"))

    # Clear the pending data from memory so it can't be triggered twice
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
    conn = get_db()
    cur  = conn.cursor()

    for item in failed_tickets:
        token, name, email = item["token"], item["name"], item["email"]
        try:
            qr_path = QR_DIR / f"{token}.png"
            if not qr_path.exists():
                qr_path = mailer.generate_qr_image(token)
            mailer.send_pass_email(name, email, token, qr_path)
            cur.execute("UPDATE tickets SET email_status='sent' WHERE token=?", (token,))
            conn.commit()
            with progress_lock:
                progress_state["sent"] += 1
        except Exception as exc:
            print(f"[RESEND ERROR] {email}: {exc}")
            cur.execute("UPDATE tickets SET email_status='failed' WHERE token=?", (token,))
            conn.commit()
            with progress_lock:
                progress_state["failed"] += 1

    conn.close()
    with progress_lock:
        progress_state["running"] = False


@app.route("/resend-failed", methods=["POST"])
@login_required
def resend_failed():
    global progress_state
    conn = get_db()
    failed = [dict(r) for r in conn.execute(
        "SELECT token,name,email FROM tickets WHERE email_status='failed'"
    ).fetchall()]
    conn.close()

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
# GATE VERIFICATION  (public – no login required)
# ---------------------------------------------------------------

@app.route("/check/<token>")
def check_token(token: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    cur  = conn.cursor()

    cur.execute(
        "UPDATE tickets SET used=1, used_at=? WHERE token=? AND used=0",
        (now, token),
    )
    changed = cur.rowcount
    conn.commit()

    if changed == 1:
        row = cur.execute("SELECT name FROM tickets WHERE token=?", (token,)).fetchone()
        conn.close()
        name = row["name"] if row else "Attendee"
        return render_template(
            "verify.html",
            event_name=EVENT_NAME,
            status="ALLOWED",
            icon="✅",
            name=name,
            message="Entry granted. Welcome to the event!",
        ), 200

    row = cur.execute(
        "SELECT name, used_at FROM tickets WHERE token=?", (token,)
    ).fetchone()
    conn.close()

    if row:
        return render_template(
            "verify.html",
            event_name=EVENT_NAME,
            status="ALREADY USED",
            icon="⚠️",
            name=row["name"],
            message=f"This pass was already used at {row['used_at'] or 'an earlier time'}.",
        ), 409

    return render_template(
        "verify.html",
        event_name=EVENT_NAME,
        status="INVALID",
        icon="❌",
        name=None,
        message="This ticket token is not found in the system.",
    ), 404


# ---------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
