import csv
import io
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

# In-memory storage for pending CSV uploads and background worker progress
pending_uploads = {}
progress_state = {
    "running": False,
    "sent": 0,
    "skipped": 0,
    "failed": 0,
    "total": 0,
}
progress_lock = threading.Lock()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            flash("Please log in with the organizer password.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


@app.context_processor
def inject_globals():
    return {"config_event_name": EVENT_NAME}


# ---------------------------------------------------------
# AUTHENTICATION ROUTES
# ---------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        submitted_pw = request.form.get("password", "")
        if submitted_pw == ORGANIZER_PASSWORD:
            session["logged_in"] = True
            session.permanent = True
            flash("Welcome! Logged in as Event Organizer.", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Incorrect organizer password. Please try again.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# ---------------------------------------------------------
# ORGANIZER DASHBOARD & DOWNLOAD
# ---------------------------------------------------------

@app.route("/")
@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS c FROM tickets")
    total = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) AS c FROM tickets WHERE email_status = 'sent'")
    sent_emails = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) AS c FROM tickets WHERE email_status = 'failed'")
    failed_emails = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) AS c FROM tickets WHERE used = 1")
    entered = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) AS c FROM tickets WHERE used = 0")
    not_entered = cursor.fetchone()["c"]

    cursor.execute("SELECT * FROM tickets ORDER BY rowid DESC")
    attendees = cursor.fetchall()
    conn.close()

    stats = {
        "total": total,
        "sent_emails": sent_emails,
        "failed_emails": failed_emails,
        "entered": entered,
        "not_entered": not_entered,
    }

    return render_template("dashboard.html", stats=stats, attendees=attendees)


@app.route("/download/not-entered")
@login_required
def download_not_entered():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name, email FROM tickets WHERE used = 0 ORDER BY name COLLATE NOCASE ASC")
    rows = cursor.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["name", "email"])
    for r in rows:
        writer.writerow([r["name"], r["email"]])

    csv_data = output.getvalue()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=not_entered_attendees.csv"},
    )


# ---------------------------------------------------------
# UPLOAD & PASS GENERATION
# ---------------------------------------------------------

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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
            reader = csv.DictReader(io.StringIO(content))
        except Exception as e:
            flash(f"Error reading CSV file: {e}", "danger")
            return redirect(url_for("upload"))

        if not reader.fieldnames:
            flash("Uploaded CSV file appears to be empty.", "danger")
            return redirect(url_for("upload"))

        # Normalize header keys
        header_map = {col.strip().lower(): col for col in reader.fieldnames}
        name_key = header_map.get("name")
        email_key = header_map.get("email")

        if not name_key or not email_key:
            flash("CSV validation failed: File must contain 'name' and 'email' columns.", "danger")
            return redirect(url_for("upload"))

        valid_rows = []
        invalid_rows = 0

        for row in reader:
            name_val = (row.get(name_key) or "").strip()
            email_val = (row.get(email_key) or "").strip()

            if not name_val or not email_val:
                invalid_rows += 1
                continue

            if not EMAIL_REGEX.match(email_val):
                invalid_rows += 1
                continue

            valid_rows.append({"name": name_val, "email": email_val})

        if not valid_rows:
            flash("No valid attendee rows found in the uploaded file.", "danger")
            return redirect(url_for("upload"))

        session_id = session.get("_id", "admin_session")
        pending_uploads[session_id] = valid_rows

        if invalid_rows > 0:
            flash(f"Loaded {len(valid_rows)} valid rows ({invalid_rows} rows skipped due to missing name or invalid email).", "warning")
        else:
            flash(f"Successfully loaded and validated {len(valid_rows)} attendees.", "success")

        return render_template(
            "upload.html",
            preview_rows=valid_rows[:10],
            total_uploaded_rows=len(valid_rows),
        )

    return render_template("upload.html", preview_rows=None)


def worker_generate_passes(attendees):
    """Background thread worker to generate tokens, QR codes, and send emails."""
    global progress_state

    conn = get_db()
    cursor = conn.cursor()

    for item in attendees:
        name = item["name"]
        email = item["email"]

        # Check if email is already in database
        cursor.execute("SELECT 1 FROM tickets WHERE email = ?", (email,))
        if cursor.fetchone() is not None:
            with progress_lock:
                progress_state["skipped"] += 1
            continue

        token = secrets.token_urlsafe(24)

        try:
            # Save record as pending
            cursor.execute(
                "INSERT INTO tickets (token, name, email, used, used_at, email_status) VALUES (?, ?, ?, 0, NULL, 'pending')",
                (token, name, email),
            )
            conn.commit()

            # Create QR image
            qr_path = mailer.generate_qr_image(token)

            # Send email
            mailer.send_pass_email(name, email, token, qr_path)

            cursor.execute("UPDATE tickets SET email_status = 'sent' WHERE token = ?", (token,))
            conn.commit()

            with progress_lock:
                progress_state["sent"] += 1

        except Exception as e:
            cursor.execute("UPDATE tickets SET email_status = 'failed' WHERE token = ?", (token,))
            conn.commit()
            with progress_lock:
                progress_state["failed"] += 1
            print(f"[MAILER ERROR] Failed to send email to {email}: {e}")

    conn.close()
    with progress_lock:
        progress_state["running"] = False


@app.route("/generate-passes", methods=["POST"])
@login_required
def generate_passes():
    global progress_state

    session_id = session.get("_id", "admin_session")
    attendees = pending_uploads.get(session_id, [])

    if not attendees:
        flash("No pending attendee list found. Please upload a CSV first.", "warning")
        return redirect(url_for("upload"))

    with progress_lock:
        progress_state = {
            "running": True,
            "sent": 0,
            "skipped": 0,
            "failed": 0,
            "total": len(attendees),
        }

    # Start sending in a background thread so the request never times out
    thread = threading.Thread(target=worker_generate_passes, args=(attendees,), daemon=True)
    thread.start()

    return redirect(url_for("progress"))


@app.route("/progress")
@login_required
def progress():
    with progress_lock:
        current_progress = dict(progress_state)
    return render_template("progress.html", progress=current_progress)


@app.route("/progress/status")
@login_required
def progress_status():
    with progress_lock:
        return jsonify(progress_state)


def worker_resend_failed(failed_tickets):
    """Background worker to retry sending emails to failed attendees."""
    global progress_state

    conn = get_db()
    cursor = conn.cursor()

    for item in failed_tickets:
        token = item["token"]
        name = item["name"]
        email = item["email"]

        try:
            qr_path = QR_DIR / f"{token}.png"
            if not qr_path.exists():
                qr_path = mailer.generate_qr_image(token)

            mailer.send_pass_email(name, email, token, qr_path)

            cursor.execute("UPDATE tickets SET email_status = 'sent' WHERE token = ?", (token,))
            conn.commit()
            with progress_lock:
                progress_state["sent"] += 1

        except Exception as e:
            cursor.execute("UPDATE tickets SET email_status = 'failed' WHERE token = ?", (token,))
            conn.commit()
            with progress_lock:
                progress_state["failed"] += 1
            print(f"[RESEND ERROR] Failed to resend email to {email}: {e}")

    conn.close()
    with progress_lock:
        progress_state["running"] = False


@app.route("/resend-failed", methods=["POST"])
@login_required
def resend_failed():
    global progress_state

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT token, name, email FROM tickets WHERE email_status = 'failed'")
    failed_tickets = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if not failed_tickets:
        flash("No failed emails to resend.", "info")
        return redirect(url_for("dashboard"))

    with progress_lock:
        progress_state = {
            "running": True,
            "sent": 0,
            "skipped": 0,
            "failed": 0,
            "total": len(failed_tickets),
        }

    thread = threading.Thread(target=worker_resend_failed, args=(failed_tickets,), daemon=True)
    thread.start()

    flash(f"Started resending {len(failed_tickets)} failed pass(es) in background.", "info")
    return redirect(url_for("progress"))


# ---------------------------------------------------------
# GATE VERIFICATION ROUTE (PUBLIC)
# ---------------------------------------------------------

@app.route("/check/<token>")
def check_token(token: str):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()
    cursor = conn.cursor()

    # Single atomic update where used is 0
    cursor.execute(
        "UPDATE tickets SET used = 1, used_at = ? WHERE token = ? AND used = 0",
        (now_str, token),
    )
    rows_changed = cursor.rowcount
    conn.commit()

    if rows_changed == 1:
        cursor.execute("SELECT name FROM tickets WHERE token = ?", (token,))
        row = cursor.fetchone()
        name = row["name"] if row else "Attendee"
        conn.close()
        return (
            render_template(
                "verify.html",
                event_name=EVENT_NAME,
                status="ALLOWED",
                icon="✅",
                name=name,
                message="Entry granted. Welcome to the event!",
            ),
            200,
        )

    # Check whether the token exists
    cursor.execute("SELECT name, used_at FROM tickets WHERE token = ?", (token,))
    row = cursor.fetchone()
    conn.close()

    if row is not None:
        used_time = row["used_at"] or "earlier"
        return (
            render_template(
                "verify.html",
                event_name=EVENT_NAME,
                status="ALREADY USED",
                icon="⚠️",
                name=row["name"],
                message=f"This pass was already used at {used_time}.",
            ),
            409,
        )

    # Token doesn't exist
    return (
        render_template(
            "verify.html",
            event_name=EVENT_NAME,
            status="INVALID",
            icon="❌",
            name=None,
            message="This ticket token is not found in the system.",
        ),
        404,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
