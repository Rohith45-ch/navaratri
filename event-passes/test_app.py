import unittest
import os
import shutil
import tempfile
from pathlib import Path

# Set test environment
os.environ["ORGANIZER_PASSWORD"] = "testpass"
os.environ["FLASK_SECRET_KEY"] = "test-secret"
os.environ["EVENT_NAME"] = "NAITRA 26'"

import config
import db
import mailer
import sheets_sync
from app import app


class TestEventPassesApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        cls.client = app.test_client()

    def setUp(self):
        # Clean tickets table for each test
        conn = db.get_conn()
        conn.execute("DELETE FROM tickets")
        conn.commit()
        conn.close()

    def test_database_insert_and_stats(self):
        self.assertFalse(db.email_exists("user@example.com"))
        db.insert_ticket("token123", "Alice Smith", "user@example.com")
        self.assertTrue(db.email_exists("user@example.com"))

        stats = db.get_stats()
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["sent"], 0)
        self.assertEqual(stats["failed"], 0)
        self.assertEqual(stats["entered"], 0)
        self.assertEqual(stats["not_entered"], 1)

    def test_check_in_lifecycle(self):
        token = "test_valid_token_xyz"
        db.insert_ticket(token, "Bob Builder", "bob@example.com")

        # First scan -> ALLOWED (changed = True)
        changed, row = db.check_in(token)
        self.assertTrue(changed)
        self.assertIsNotNone(row)
        self.assertEqual(row["name"], "Bob Builder")
        self.assertEqual(row["used"], 1)

        # Second scan -> ALREADY USED (changed = False, but row exists)
        changed2, row2 = db.check_in(token)
        self.assertFalse(changed2)
        self.assertIsNotNone(row2)
        self.assertEqual(row2["name"], "Bob Builder")

        # Invalid token -> row is None
        changed3, row3 = db.check_in("non_existent_token")
        self.assertFalse(changed3)
        self.assertIsNone(row3)

    def test_gate_check_http_endpoints_html_and_json(self):
        token = "token_http_test"
        db.insert_ticket(token, "Charlie Brown", "charlie@example.com")

        # 1. HTML direct check
        resp = self.client.get(f"/check/{token}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"ALLOWED", resp.data)
        self.assertIn(b"Charlie Brown", resp.data)

        # 2. JSON check (used by camera scanner fetch) - should now return 409 ALREADY USED
        json_resp = self.client.get(
            f"/check/{token}",
            headers={"Accept": "application/json"}
        )
        self.assertEqual(json_resp.status_code, 409)
        data = json_resp.get_json()
        self.assertEqual(data["status"], "ALREADY USED")
        self.assertEqual(data["name"], "Charlie Brown")

        # 3. Invalid token -> 404 INVALID
        inv_resp = self.client.get(
            "/check/invalid_token_999",
            headers={"Accept": "application/json"}
        )
        self.assertEqual(inv_resp.status_code, 404)
        inv_data = inv_resp.get_json()
        self.assertEqual(inv_data["status"], "INVALID")

    def test_qr_generation(self):
        token = "token_qr_test_abc"
        qr_path = mailer.generate_qr_image(token)
        self.assertTrue(qr_path.exists())
        self.assertGreater(qr_path.stat().st_size, 100)

    def test_scan_page_loads(self):
        resp = self.client.get("/scan")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Gate QR Scanner", resp.data)
        self.assertIn(b"html5-qrcode", resp.data)

    def test_auth_protection(self):
        # Without login -> redirects to /login
        resp = self.client.get("/dashboard")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

        # With correct login -> accesses dashboard
        login_resp = self.client.post("/login", data={"password": "testpass"}, follow_redirects=True)
        self.assertEqual(login_resp.status_code, 200)
        self.assertIn(b"Gate &amp; Passes Overview", login_resp.data)

    def test_sheets_sync_graceful_handling(self):
        # When service_account.json doesn't exist, sheets_sync should log and return False without error
        res = sheets_sync.sync_to_sheet()
        self.assertFalse(res)


if __name__ == "__main__":
    unittest.main()
