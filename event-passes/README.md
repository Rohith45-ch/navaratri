# NAITRA 26' - Event Entry Passes System

A complete college event entry pass web application built in Python 3 using Flask, SQLite, QR Code generation, Gmail SMTP, Google Sheets synchronization, and a mobile browser camera scanner.

---

## 📁 Project Structure

```
event-passes/
├── app.py                  # Flask web application routes & background workers
├── db.py                   # SQLite database functions (source of truth)
├── config.py               # Centralized configuration & environment variables
├── mailer.py               # QR code generation & pass email delivery
├── sheets_sync.py          # Google Sheets one-way mirror synchronization
├── requirements.txt        # Python package dependencies
├── .gitignore              # Ignores venv, db, qr, and secrets
├── attendees_sample.csv    # 3-row sample attendee test CSV
├── README.md               # Complete setup, testing, and architecture guide
├── qr/                     # Generated QR code image files (.png)
├── secrets/                # Holds service_account.json (git-ignored)
├── static/
│   └── style.css           # Modern, responsive application styling
└── templates/
    ├── layout.html         # Base template with responsive navigation
    ├── login.html          # Organizer login page
    ├── dashboard.html      # Metrics, roster, download, and sync actions
    ├── upload.html         # CSV validation and 10-row preview
    ├── progress.html       # Real-time background pass generation progress
    ├── verify.html         # Gate result display (ALLOWED / ALREADY USED / INVALID)
    └── scan.html           # Full-screen mobile camera QR scanner
```

---

## ⚙️ Environment Variables

Set these environment variables before running the application:

| Variable | Default Value | Example | Description |
|---|---|---|---|
| `EVENT_NAME` | `NAITRA 26'` | `"NAITRA 26'"` | Name of the event on passes & headers |
| `BASE_URL` | `http://localhost:8000` | `http://192.168.1.10:8000` | Public URL encoded into the QR code |
| `ORGANIZER_PASSWORD` | `admin123` | `FestAdmin2026!` | Password required to access organizer portal |
| `FLASK_SECRET_KEY` | *(built-in default)* | `random-session-secret-string` | Secret key for Flask session signing |
| `SMTP_HOST` | `smtp.gmail.com` | `smtp.gmail.com` | Outgoing SMTP mail server |
| `SMTP_PORT` | `465` | `465` | SMTP port (465 for SSL, 587 for STARTTLS) |
| `SENDER_EMAIL` | *(empty)* | `organizer@gmail.com` | Gmail account sending the entry passes |
| `SMTP_PASSWORD` | *(empty)* | `abcd efgh ijkl mnop` | 16-character Google App Password (not your normal Gmail password) |
| `SHEET_ID` | *(empty)* | `1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms` | ID of the Google Sheet to mirror SQLite to |
| `SERVICE_ACCOUNT_KEY`| `secrets/service_account.json` | `secrets/service_account.json` | Path to Google Service Account JSON key |
| `DB_PATH` | `tickets.db` | `tickets.db` | Path to SQLite database file |

---

## 🚀 Installation & Running

### 1. Prerequisites
- Python 3.10+ (Ubuntu 22.04 / 24.04 include Python 3.12)
- Virtual environment tool (`python3-venv`)

### 2. Set Up Virtual Environment & Dependencies
```bash
cd event-passes

# Create virtual environment
python3 -m venv venv

# Activate and install dependencies
venv/bin/pip install -r requirements.txt
```

### 3. Run the Application
```bash
# Optional: export your custom environment variables
export ORGANIZER_PASSWORD="admin123"
export SENDER_EMAIL="your-email@gmail.com"
export SMTP_PASSWORD="your-app-password"
export SHEET_ID="your-google-sheet-id"

# Run the Flask app
venv/bin/python app.py
```

Open your browser at:
- **Organizer Portal:** [http://localhost:8000/login](http://localhost:8000/login) (Password: `admin123` by default)
- **Gate Camera Scanner:** [http://localhost:8000/scan](http://localhost:8000/scan)

---

## 📊 Google Sheets Setup (Mirroring SQLite)

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g., `Event-Passes-Sync`).
3. Under **APIs & Services > Library**, enable:
   - **Google Sheets API**
   - **Google Drive API**
4. Under **APIs & Services > Credentials**:
   - Click **Create Credentials > Service account**.
   - Name it (e.g., `sheet-syncer`) and click **Done**.
   - Click into the created service account, navigate to the **Keys** tab, select **Add Key > Create new key > JSON**.
   - Save the downloaded JSON file to `event-passes/secrets/service_account.json`.
5. Create a new Google Sheet in Google Drive.
6. Click **Share** on your Google Sheet and share it with the `client_email` address found in your `service_account.json` file. Give it **Editor** permissions.
7. Copy the Sheet ID from the browser URL:
   `https://docs.google.com/spreadsheets/d/`**`<SHEET_ID>`**`/edit`
8. Export the ID:
   ```bash
   export SHEET_ID="your-sheet-id-here"
   ```

---

## 🔒 Important Operational Notes

1. **Camera access requires HTTPS:**
   - Modern phone browsers (Chrome, Safari, Firefox) **block camera access on unencrypted HTTP** connections (except on `localhost`).
   - For testing on your laptop, `http://localhost:8000` has full camera permissions.
   - For gate staff using phones, deploy the app on a service that provides automatic SSL/HTTPS (e.g., Render, Railway, fly.io, or behind Cloudflare/Caddy/Nginx).

2. **Email rate limits:**
   - Standard personal Gmail accounts allow sending approximately 500 emails per 24 hours. Google Workspace accounts allow up to 2,000/day.
   - If sending hits an SMTP quota limit, the app marks unsent tickets as `failed`. You can safely click **Resend Failed** the next day without re-emailing anyone who already received their pass.

3. **Source of Truth:**
   - Local SQLite (`tickets.db`) is the absolute source of truth.
   - Sync to Google Sheet runs asynchronously in the background and will never block or fail gate check-ins if the internet drops.
