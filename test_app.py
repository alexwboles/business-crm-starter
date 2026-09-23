import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path

from app import CRMHandler, CRMStore


class CRMStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = CRMStore(Path(self.temp.name) / "test.db")

    def tearDown(self):
        self.temp.cleanup()

    def sample(self, **updates):
        payload = {
            "name": "Alex Client",
            "company": "Acme",
            "email": "alex@example.test",
            "stage": "New",
            "value": 1200,
        }
        payload.update(updates)
        return payload

    def test_add_and_list_lead(self):
        created = self.store.add_lead(self.sample())
        self.assertEqual(created["email"], "alex@example.test")
        self.assertEqual(len(self.store.list_leads()), 1)

    def test_duplicate_email_is_rejected(self):
        self.store.add_lead(self.sample())
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.store.add_lead(self.sample(name="Someone Else"))

    def test_invalid_email_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "valid email"):
            self.store.add_lead(self.sample(email="not-an-email"))

    def test_invalid_stage_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid pipeline"):
            self.store.add_lead(self.sample(stage="Maybe"))

    def test_overdue_followup_is_high_priority(self):
        lead = self.store.add_lead(
            self.sample(next_followup=str(date.today() - timedelta(days=1)))
        )
        self.assertEqual(lead["priority"], "High")
        self.assertEqual(lead["recommended_action"], "Follow up today")

    def test_stage_update_changes_dashboard_totals(self):
        lead = self.store.add_lead(self.sample(value=1500))
        self.store.update_stage(lead["id"], "Won")
        dashboard = self.store.dashboard()
        self.assertEqual(dashboard["open_count"], 0)
        self.assertEqual(dashboard["won_value"], 1500)

    def test_seed_is_idempotent(self):
        self.store.seed_demo()
        self.store.seed_demo()
        self.assertEqual(len(self.store.list_leads()), 4)


class CRMHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        store = CRMStore(Path(cls.temp.name) / "http.db")
        handler = type("TestHandler", (CRMHandler,), {"store": store})
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp.cleanup()

    def request(self, path, method="GET", payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            return response.status, json.load(response)

    def test_dashboard_endpoint(self):
        status, body = self.request("/api/dashboard")
        self.assertEqual(status, 200)
        self.assertIn("stage_counts", body)

    def test_create_lead_endpoint(self):
        status, body = self.request(
            "/api/leads",
            "POST",
            {"name": "HTTP Lead", "email": "http@example.test", "value": 300},
        )
        self.assertEqual(status, 201)
        self.assertEqual(body["name"], "HTTP Lead")


if __name__ == "__main__":
    unittest.main()
