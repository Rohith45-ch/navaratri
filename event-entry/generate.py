import argparse
import csv
import os
import secrets
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

import qrcode

from config import (
    BASE_URL,
    EVENT_NAME,
    QR_DIR,
    SENDER_EMAIL,
    SENDER_PASSWORD,
    SMTP_HOST,
    SMTP_PORT,
    get_db,
)


def create_qr_code(token: str, check_url: str, output_path: Path) -> Path:
    """Generate a high-contrast QR code image containing the verification URL."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(check_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(str(output_path))
    return output_path


def send_ticket_email(name: str, email: str, token: str, qr_path: Path, check_url: str) -> None:
    """Send entry ticket email with QR code attachment."""
    msg = EmailMessage()
    msg["Subject"] = f"Your Entry Pass - {EVENT_NAME}"
    msg["From"] = SENDER_EMAIL or "noreply@evententry.local"
    msg["To"] = email

    text_content = f"""Hello {name},

Here is your single-use entry pass for {EVENT_NAME}.

IMPORTANT NOTICE:
- This entry pass works only once.
- Once scanned and verified at the entrance gate, it will be immediately marked as used and cannot be used again.

Please find your QR code pass attached to this email. You can present this QR code on your mobile device or printed out at the gate.

Verification Link:
{check_url}

We look forward to seeing you at {EVENT_NAME}!
"""

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1f2937; line-height: 1.5; }}
    .card {{ max-width: 540px; margin: 20px auto; padding: 24px; border: 1px solid #e5e7eb; border-radius: 12px; background: #ffffff; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }}
    .header {{ font-size: 20px; font-weight: 700; color: #111827; margin-bottom: 8px; }}
    .notice {{ background: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px; margin: 16px 0; border-radius: 4px; font-size: 14px; color: #92400e; }}
    .link-box {{ word-break: break-all; font-size: 13px; color: #4b5563; background: #f3f4f6; padding: 10px; border-radius: 6px; margin: 12px 0; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">{EVENT_NAME}</div>
    <p>Hello <strong>{name}</strong>,</p>
    <p>Thank you for registering! Your official entry pass is attached.</p>
    <div class="notice">
      <strong>Single-Use Policy:</strong> This entry pass works <strong>ONLY ONCE</strong>. It will be validated and permanently deactivated upon your first scan at the gate.
    </div>
    <p>Present the attached QR code image at the gate scanner.</p>
    <div class="link-box">
      <strong>Verification URL:</strong><br>
      <a href="{check_url}">{check_url}</a>
    </div>
  </div>
</body>
</html>
"""

    msg.set_content(text_content)
    msg.add_alternative(html_content, subtype="html")

    with open(qr_path, "rb") as f:
        img_bytes = f.read()

    msg.add_attachment(
        img_bytes,
        maintype="image",
        subtype="png",
        filename=f"ticket_{token}.png",
    )

    if SMTP_PORT == 465:
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20)
    else:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
        server.ehlo()
        try:
            if server.has_extn("STARTTLS"):
                server.starttls()
                server.ehlo()
        except smtplib.SMTPNotSupportedError:
            pass

    if SENDER_PASSWORD:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)

    server.send_message(msg)
    server.quit()


def process_csv(
    csv_path: str,
    skip_email: bool = False,
    name_override: str | None = None,
    email_override: str | None = None,
    limit: int | None = None,
) -> None:
    if not os.path.exists(csv_path):
        print(f"Error: CSV file '{csv_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    conn = get_db()
    cursor = conn.cursor()

    sent_count = 0
    skipped_count = 0
    failed_count = 0

    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            print("Error: CSV file is empty.", file=sys.stderr)
            sys.exit(1)

        # Smart column header detection
        raw_headers = list(reader.fieldnames)
        
        def match_column(candidates, preferred=None):
            if preferred:
                for h in raw_headers:
                    if h.strip().lower() == preferred.strip().lower():
                        return h
            for candidate in candidates:
                for h in raw_headers:
                    if h.strip().lower() == candidate:
                        return h
            for candidate in candidates:
                for h in raw_headers:
                    if candidate in h.strip().lower():
                        return h
            return None

        name_col = match_column(["name", "full name", "fullname", "student name", "attendee name", "participant name", "candidate name"], name_override)
        email_col = match_column(["email", "email address", "email id", "mail", "e-mail", "email_id"], email_override)

        if not name_col or not email_col:
            print(f"Error: Could not identify name and email columns in CSV. Available headers: {raw_headers}", file=sys.stderr)
            print("Please specify columns explicitly using --name-col and --email-col.", file=sys.stderr)
            sys.exit(1)

        print(f"Detected columns -> Name: '{name_col}', Email: '{email_col}'")

        for row in reader:
            name = (row.get(name_col) or "").strip()
            email = (row.get(email_col) or "").strip()

            if not name or not email:
                continue

            # Check if email already exists in database
            cursor.execute("SELECT 1 FROM tickets WHERE email = ?", (email,))
            if cursor.fetchone() is not None:
                skipped_count += 1
                print(f"[SKIPPED] {name} ({email}) - Already registered in database.")
                continue

            # Generate token and URLs
            token = secrets.token_urlsafe(24)
            check_url = f"{BASE_URL}{token}"
            qr_file = QR_DIR / f"{token}.png"

            try:
                # Insert record into database
                cursor.execute(
                    "INSERT INTO tickets (token, name, email, used, used_at) VALUES (?, ?, ?, 0, NULL)",
                    (token, name, email),
                )

                # Create QR code image
                create_qr_code(token, check_url, qr_file)

                # Send email unless skipped via flag
                if not skip_email:
                    send_ticket_email(name, email, token, qr_file, check_url)

                conn.commit()
                sent_count += 1
                status_msg = "Created & Emailed" if not skip_email else "Created (Email skipped)"
                print(f"[SENT] {name} ({email}) -> {status_msg} [Token: {token[:8]}...]")

            except Exception as e:
                conn.rollback()
                if qr_file.exists():
                    try:
                        qr_file.unlink()
                    except OSError:
                        pass
                failed_count += 1
                print(f"[FAILED] Error sending to {name} ({email}): {e}", file=sys.stderr)

            if limit is not None and sent_count >= limit:
                print(f"\nReached requested processing limit of {limit} attendees.")
                break

    conn.close()

    print("\n" + "=" * 50)
    print("GENERATION SUMMARY")
    print("=" * 50)
    print(f"Sent / Generated : {sent_count}")
    print(f"Skipped          : {skipped_count}")
    print(f"Failed           : {failed_count}")
    print(f"Total Processed  : {sent_count + skipped_count + failed_count}")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(
        description="Generate single-use QR entry passes from an attendee CSV and email them."
    )
    parser.add_argument("csv_file", help="Path to attendees CSV file (e.g. attendees.csv)")
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Generate QR codes and DB entries without sending emails (useful for offline testing)",
    )
    parser.add_argument(
        "--name-col",
        type=str,
        default=None,
        help="Custom header name for attendee name column",
    )
    parser.add_argument(
        "--email-col",
        type=str,
        default=None,
        help="Custom header name for attendee email column",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of attendees to process in this run",
    )
    args = parser.parse_args()

    process_csv(
        args.csv_file,
        skip_email=args.no_email,
        name_override=args.name_col,
        email_override=args.email_col,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
