import smtplib
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
)


def generate_qr_image(token: str) -> Path:
    """Generate high-contrast QR code pointing to /check/<token> and save to qr/<token>.png."""
    check_url = f"{BASE_URL}/check/{token}"
    qr_path = QR_DIR / f"{token}.png"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(check_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(str(qr_path))
    return qr_path


def send_pass_email(name: str, email: str, token: str, qr_path: Path) -> None:
    """Send entry ticket pass with single-use warning and attached QR image."""
    check_url = f"{BASE_URL}/check/{token}"

    msg = EmailMessage()
    msg["Subject"] = f"Your Entry Pass - {EVENT_NAME}"
    msg["From"] = SENDER_EMAIL or "noreply@eventpasses.local"
    msg["To"] = email

    text_body = f"""Hello {name},

Here is your official single-use entry pass for {EVENT_NAME}.

IMPORTANT NOTICE:
- This QR code pass works ONLY ONCE.
- When scanned and verified at the entrance gate, it will be immediately marked as used and cannot be reused.

Please find your QR entry pass attached to this email. You can present this code on your phone or print it out.

Verification Link:
{check_url}

We look forward to seeing you at {EVENT_NAME}!
"""

    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1f2937; line-height: 1.5; }}
    .card {{ max-width: 560px; margin: 20px auto; padding: 24px; border: 1px solid #e5e7eb; border-radius: 12px; background: #ffffff; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }}
    .title {{ font-size: 20px; font-weight: 700; color: #111827; margin-bottom: 8px; }}
    .alert {{ background: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px; margin: 16px 0; border-radius: 4px; font-size: 14px; color: #92400e; }}
    .url-box {{ word-break: break-all; font-size: 13px; color: #4b5563; background: #f3f4f6; padding: 10px; border-radius: 6px; margin: 14px 0; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="title">{EVENT_NAME}</div>
    <p>Hello <strong>{name}</strong>,</p>
    <p>Thank you for registering! Your official gate entry pass is ready.</p>
    <div class="alert">
      ⚠️ <strong>Single-Use Pass:</strong> This entry ticket works <strong>ONLY ONCE</strong>. Once scanned and verified at the gate, it will be permanently deactivated.
    </div>
    <p>Please present the attached QR code image at the entrance gate scanner.</p>
    <div class="url-box">
      <strong>Gate Verification URL:</strong><br>
      <a href="{check_url}">{check_url}</a>
    </div>
  </div>
</body>
</html>
"""

    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    with open(qr_path, "rb") as f:
        img_bytes = f.read()

    msg.add_attachment(
        img_bytes,
        maintype="image",
        subtype="png",
        filename=f"ticket_{token}.png",
    )

    # Port 465 uses SSL directly (Gmail standard)
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
