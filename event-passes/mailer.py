import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path

import qrcode

import config

logger = logging.getLogger(__name__)


def generate_qr_image(token: str) -> Path:
    """
    Generate a high-contrast QR code pointing to BASE_URL/check/<token>
    and save to qr/<token>.png. Returns the Path.
    """
    check_url = f"{config.BASE_URL}/check/{token}"
    qr_path = config.QR_DIR / f"{token}.png"

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
    """
    Send entry pass email with event name in subject, greeting using name,
    explicit single-use warning, and the QR code image attached.
    """
    check_url = f"{config.BASE_URL}/check/{token}"
    sender_addr = config.SENDER_EMAIL or "noreply@eventpasses.local"

    msg = EmailMessage()
    msg["Subject"] = f"Your Entry Pass - {config.EVENT_NAME}"
    msg["From"] = sender_addr
    msg["To"] = email

    text_body = f"""Hello {name},

Here is your official single-use entry pass for {config.EVENT_NAME}.

IMPORTANT NOTICE:
- This QR code pass works ONLY ONCE.
- When scanned and verified at the entrance gate, it will be immediately marked as used and cannot be reused.

Please find your QR entry pass attached to this email. You can present this code on your phone or print it out.

Verification Link:
{check_url}

We look forward to seeing you at {config.EVENT_NAME}!
"""

    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1f2937; line-height: 1.5; margin: 0; padding: 20px; background-color: #f9fafb; }}
    .card {{ max-width: 560px; margin: 0 auto; padding: 32px; border: 1px solid #e5e7eb; border-radius: 16px; background: #ffffff; box-shadow: 0 4px 12px rgba(0,0,0,0.06); }}
    .title {{ font-size: 22px; font-weight: 800; color: #111827; margin-bottom: 12px; }}
    .alert {{ background: #fef3c7; border-left: 4px solid #f59e0b; padding: 14px 16px; margin: 20px 0; border-radius: 6px; font-size: 14px; color: #92400e; font-weight: 500; }}
    .url-box {{ word-break: break-all; font-size: 13px; color: #4b5563; background: #f3f4f6; padding: 12px; border-radius: 8px; margin: 18px 0; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="title">{config.EVENT_NAME}</div>
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

    if not config.SENDER_PASSWORD:
        raise ValueError("SMTP_PASSWORD is not configured in environment variables.")

    if config.SMTP_PORT == 465:
        server = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=20)
    else:
        server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20)
        server.ehlo()
        if server.has_extn("STARTTLS"):
            server.starttls()
            server.ehlo()

    try:
        server.login(config.SENDER_EMAIL, config.SENDER_PASSWORD)
        server.send_message(msg)
    finally:
        server.quit()
