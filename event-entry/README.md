# College Event Entry Verification System

A command-line Python application for managing college event entry with single-use QR tickets, automated email delivery, and mobile-friendly gate verification.

---

## Features

- **Unique Single-Use QR Passes**: Cryptographically secure 24-byte URL-safe tokens generated using Python's `secrets` module.
- **Automated Email Delivery**: Generates high-contrast QR codes and emails them directly to attendees as attachments with single-use notices.
- **Safe Re-runs**: Automatically checks the SQLite database and skips attendees who have already been processed.
- **Race-Condition-Proof Verification**: Executes an atomic single database update (`UPDATE ... WHERE token = ? AND used = 0`) to guarantee that tickets can only be used once even under rapid scanning.
- **Mobile-Optimized Gate Interface**: Bold, high-contrast, color-coded visual cards (`ALLOWED` in green, `ALREADY USED` in orange/yellow, `INVALID` in red) designed for gatekeepers at arm's length.
- **Reporting & Reconciliation**: Instant terminal summary of attendance stats and automatic export of unentered attendees to `not_entered.csv`.

---

## Project Structure

```text
event-entry/
├── config.py             # Centralized configuration (event name, URLs, SMTP, DB)
├── generate.py           # CLI script to process CSV, generate QR passes, and email attendees
├── verify.py             # Flask gate verification server (runs on 0.0.0.0:8000)
├── report.py             # CLI reporting tool and unentered CSV exporter
├── requirements.txt      # Dependency list (Flask, qrcode, Pillow)
├── attendees_sample.csv  # Sample input CSV of attendees
├── qr/                   # Storage folder for generated QR code images
└── README.md             # Documentation and usage guide
```

---

## 1. Setup & Installation

### Step 1: Create and Activate a Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

---

## 2. Configuration & SMTP Credentials

All configuration parameters are defined in `config.py` and can be customized through environment variables:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `EVENT_NAME` | Name of the college event | `College Annual Cultural Fest 2026` |
| `BASE_URL` | Public verification URL base | `http://localhost:8000/check/` |
| `SMTP_HOST` | Outgoing SMTP mail server | `smtp.gmail.com` |
| `SMTP_PORT` | Outgoing SMTP port | `587` |
| `SENDER_EMAIL` | Sender email address | `rohithkumar118a@gmail.com` |
| `SMTP_PASSWORD`| App Password for sender email | *(Required from environment)* |
| `DB_PATH` | Path to SQLite database file | `tickets.db` |

### Setting Your Gmail App Password
> [!IMPORTANT]
> When using Gmail, standard account passwords will **not** work. You must use an **App Password**:
> 1. Go to your [Google Account Security](https://myaccount.google.com/security).
> 2. Enable **2-Step Verification** if not already enabled.
> 3. Search for **App passwords** (or visit `https://myaccount.google.com/apppasswords`).
> 4. Create a new App Password named `EventEntry`.
> 5. Copy the 16-character code and set it in your terminal session:

```bash
export SMTP_PASSWORD="your-16-char-app-password"
```

*(You can also set `export SENDER_EMAIL="your_email@gmail.com"` if using a different account).*

---

## 3. How to Run

### Step 1: Generate QR Passes and Email Attendees
Ensure your attendee CSV has `name` and `email` columns:

```bash
python generate.py attendees_sample.csv
```

- Each attendee receives an email with their ticket attached and verification details.
- Progress is printed for each person (`[SENT]`, `[SKIPPED]`, or `[FAILED]`).
- Re-running the script safely skips attendees whose emails already exist in the database.
- *(Optional)* For offline testing without sending emails, run with `--no-email`:
  ```bash
  python generate.py attendees_sample.csv --no-email
  ```

### Step 2: Start the Gate Verification Server
Start the Flask verification server:

```bash
python verify.py
```
The server binds to `0.0.0.0:8000`.

> [!NOTE]
> **Gate Phone Accessibility**:
> For smartphones at the gate to scan and verify QR codes, gate phones must be able to reach the server.
> - **Same Local Wi-Fi**: Set `BASE_URL` to the computer's local IP (e.g. `export BASE_URL="http://192.168.1.50:8000/check/"`).
> - **Public Internet / Tunnels**: Use a tunnel like `ngrok` or `cloudflared` (e.g. `ngrok http 8000`) and set `BASE_URL` to the public tunnel URL (`export BASE_URL="https://your-domain.ngrok-free.app/check/"`).

### Step 3: Test a QR Pass by Scanning Twice
1. Open the verification URL (or scan the generated QR code in `qr/<token>.png`).
2. **First scan**: Shows **`ALLOWED`** in bold green with the attendee's name (HTTP 200).
3. **Second scan (refresh page)**: Shows **`ALREADY USED`** in bold orange with the timestamp of first entry (HTTP 409).
4. **Invalid URL**: Visiting an unknown token (e.g., `http://localhost:8000/check/fake_token`) shows **`INVALID`** in red (HTTP 404).

### Step 4: Run the Attendance Report
At any time during or after the event, run:

```bash
python report.py
```

This prints:
- Total registered attendees
- Total entered attendees
- Total unentered attendees
- Full list of names and emails of unentered attendees
- Automatically saves unentered attendees to `not_entered.csv`.

---

## Database Schema

Stored in `tickets.db` (created automatically on first run):

| Column | Type | Description |
| :--- | :--- | :--- |
| `token` | `TEXT PRIMARY KEY` | 24-byte URL-safe secret token |
| `name` | `TEXT NOT NULL` | Attendee full name |
| `email` | `TEXT NOT NULL` | Attendee email address |
| `used` | `INTEGER DEFAULT 0`| `0` = unused, `1` = used |
| `used_at` | `TEXT` | Timestamp of entry verification |
