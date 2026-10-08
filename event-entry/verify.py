import html
from datetime import datetime, timezone
from flask import Flask, render_template_string

from config import EVENT_NAME, get_db

app = Flask(__name__)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>{{ status }} - Entry Verification</title>
  <style>
    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      padding: 24px;
      text-align: center;
      color: #ffffff;
      {% if status == 'ALLOWED' %}
      background: linear-gradient(135deg, #15803d 0%, #16a34a 100%);
      {% elif status == 'ALREADY USED' %}
      background: linear-gradient(135deg, #c2410c 0%, #ea580c 100%);
      {% else %}
      background: linear-gradient(135deg, #991b1b 0%, #dc2626 100%);
      {% endif %}
    }
    .card {
      background: rgba(0, 0, 0, 0.25);
      backdrop-filter: blur(8px);
      -webkit-backdrop-filter: blur(8px);
      border-radius: 28px;
      padding: 48px 32px;
      max-width: 520px;
      width: 100%;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.35);
      border: 2px solid rgba(255, 255, 255, 0.2);
    }
    .icon {
      font-size: 5rem;
      line-height: 1;
      margin-bottom: 20px;
    }
    .status-text {
      font-size: 3.5rem;
      font-weight: 900;
      letter-spacing: 2px;
      line-height: 1.1;
      margin-bottom: 20px;
      text-shadow: 0 2px 10px rgba(0, 0, 0, 0.4);
    }
    .attendee-name {
      font-size: 2.2rem;
      font-weight: 700;
      background: rgba(255, 255, 255, 0.2);
      padding: 14px 24px;
      border-radius: 16px;
      margin: 16px 0 24px 0;
      word-break: break-word;
    }
    .details {
      font-size: 1.35rem;
      font-weight: 500;
      line-height: 1.5;
      opacity: 0.95;
    }
    .event-badge {
      font-size: 1.1rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 1.5px;
      opacity: 0.85;
      margin-bottom: 12px;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="event-badge">{{ event_name }}</div>
    <div class="icon">{{ icon }}</div>
    <h1 class="status-text">{{ status }}</h1>
    {% if name %}
    <div class="attendee-name">{{ name }}</div>
    {% endif %}
    <p class="details">{{ message }}</p>
  </div>
</body>
</html>
"""


@app.route("/check/<token>")
def check_token(token: str):
    # Format current local timestamp
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()
    cursor = conn.cursor()

    # Atomic single update where used is still 0
    cursor.execute(
        "UPDATE tickets SET used = 1, used_at = ? WHERE token = ? AND used = 0",
        (now_str, token),
    )
    rows_updated = cursor.rowcount
    conn.commit()

    if rows_updated == 1:
        # Success: Fetch attendee name
        cursor.execute("SELECT name FROM tickets WHERE token = ?", (token,))
        row = cursor.fetchone()
        name = row["name"] if row else "Attendee"
        conn.close()

        return (
            render_template_string(
                HTML_TEMPLATE,
                event_name=EVENT_NAME,
                status="ALLOWED",
                icon="✅",
                name=html.escape(name),
                message="Entry granted. Welcome to the event!",
            ),
            200,
        )

    # If no row was updated, check if the token exists
    cursor.execute("SELECT name, used_at FROM tickets WHERE token = ?", (token,))
    row = cursor.fetchone()
    conn.close()

    if row is not None:
        name = row["name"]
        used_time = row["used_at"] or "earlier"
        return (
            render_template_string(
                HTML_TEMPLATE,
                event_name=EVENT_NAME,
                status="ALREADY USED",
                icon="⚠️",
                name=html.escape(name),
                message=f"This pass was already used at {used_time}.",
            ),
            409,
        )

    # Token does not exist
    return (
        render_template_string(
            HTML_TEMPLATE,
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
