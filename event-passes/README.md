# College Event Entry Passes Web Application

A full-stack Flask web application for managing college event ticketing:
- Organizers log in, upload attendee CSV rosters, preview entries, and trigger automated QR code passes via email in background worker threads.
- Gatekeepers use smartphones to scan QR codes at the gate with race-condition-proof verification (`ALLOWED`, `ALREADY USED`, `INVALID`).
- Real-time dashboard tracks email deliveries, gate admissions, and exports unentered attendees.

---

## Project Structure

```text
event-passes/
├── app.py                # Main Flask application with all routes & background workers
├── mailer.py             # QR image generation and SMTP email dispatch with attachments
├── config.py             # Configuration settings, SQLite schema & connection manager
├── requirements.txt      # Python dependencies (Flask, qrcode, Pillow)
├── templates/            # HTML templates
│   ├── layout.html       # Base layout with navigation and alerts
│   ├── login.html        # Password-protected organizer login
│   ├── dashboard.html    # Statistics, roster table, CSV export, and scan test links
│   ├── upload.html       # CSV file upload, format validation, and 10-row preview
│   ├── progress.html     # Live pass generation & email delivery progress tracker
│   └── verify.html       # High-contrast mobile gate verification card
├── static/
│   └── style.css         # Modern, responsive CSS styling
├── qr/                   # Storage folder for generated QR code PNG images
└── README.md             # Documentation and usage instructions
```

---

## 1. Setup & Installation

### Step 1: Create and Activate Virtual Environment
```bash
cd /home/rohith/NAVARATRI/event-passes
python3 -m venv venv
source venv/bin/activate
```

### Step 2: Install Required Packages
```bash
pip install -r requirements.txt
```

---

## 2. Configuration & Environment Variables

All settings are centralized in `config.py`. Configure them in your environment:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `EVENT_NAME` | Name of the event displayed in passes and portal | `College Annual Cultural Fest 2026` |
| `BASE_URL` | Public base URL of server (without trailing slash) | `http://localhost:8000` |
| `SMTP_HOST` | Outgoing SMTP server | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP Port (default SSL port 465) | `465` |
| `SENDER_EMAIL` | Sender email address | `rohithkumar118a@gmail.com` |
| `SMTP_PASSWORD` | App Password for sender email account | *(Read from env, never hardcoded)* |
| `ORGANIZER_PASSWORD` | Password to access organizer portal | `admin123` |
| `SECRET_KEY` | Flask session secret key | Auto-configured |

### Setting Up Gmail App Password
> [!IMPORTANT]
> When using Gmail as the sender account, normal account passwords are not accepted. You must generate a 16-character **App Password**:
> 1. Visit your [Google Account Security](https://myaccount.google.com/security) settings.
> 2. Ensure **2-Step Verification** is turned ON.
> 3. Go to [App passwords](https://myaccount.google.com/apppasswords).
> 4. Create an App password named `EventPasses`.
> 5. Set the password in your terminal:

```bash
export SMTP_PASSWORD="your-16-char-app-password"
export ORGANIZER_PASSWORD="your_secure_organizer_password"
```

---

## 3. Running the Web Application

Start the Flask server:
```bash
python app.py
```
The server will start on `http://0.0.0.0:8000`.

---

## 4. How to Use

### Step 1: Log In as Organizer
1. Navigate to `http://localhost:8000/login` in your browser.
2. Enter the organizer password (`ORGANIZER_PASSWORD`, default: `admin123`).

### Step 2: Upload Attendee List
1. Click **Upload Attendees** (`/upload`).
2. Select a CSV file with `name` and `email` columns:
   ```csv
   name,email
   Rohith Kumar,rohithkumar118a@gmail.com
   Aarav Sharma,rohithkumar118a+guest1@gmail.com
   Priya Patel,rohithkumar118a+guest2@gmail.com
   ```
3. Click **Inspect & Preview CSV**. The app validates all emails and displays a preview of the first 10 rows.
4. Click **🚀 Generate and send passes**.

### Step 3: Track Generation Progress
- The app generates unique tokens with `secrets.token_urlsafe(24)`, saves records, renders QR codes, and sends emails in a background thread.
- The `/progress` page refreshes automatically every 3 seconds showing sent, skipped, and failed counts.
- If any email encounters an SMTP error, click **🔄 Resend Failed Emails** to retry failed recipients.

### Step 4: Gate Check-In & Verification
Gate attendants scan the QR codes on attendee phones:
- **First Scan**: Loads `http://localhost:8000/check/<token>` &rarr; Shows **`ALLOWED`** in bold green with the attendee's name (HTTP `200`).
- **Second Scan**: Reloading the link &rarr; Shows **`ALREADY USED`** in bold orange with the first entry timestamp (HTTP `409`).
- **Invalid Pass**: Scanning a fake/unknown token &rarr; Shows **`INVALID`** in red (HTTP `404`).

### Step 5: Dashboard & Attendance Export
- Monitor live attendance on `/dashboard`.
- Click **📥 Download Unentered CSV** (`/download/not-entered`) at any point to download a list of attendees who have not yet checked in.

---

## Database Schema

Stored in `tickets.db` (automatically created on first launch):

```sql
CREATE TABLE tickets (
    token TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    used INTEGER DEFAULT 0,
    used_at TEXT,
    email_status TEXT DEFAULT 'pending'
);
```
