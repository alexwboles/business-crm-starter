from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DEFAULT_DB = ROOT / "crm.db"
STAGES = ("New", "Contacted", "Qualified", "Proposal", "Won", "Lost")


class CRMStore:
    def __init__(self, db_path: str | Path = DEFAULT_DB):
        self.db_path = str(db_path)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        with closing(self.connect()) as conn, conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    company TEXT NOT NULL DEFAULT '',
                    email TEXT NOT NULL UNIQUE,
                    source TEXT NOT NULL DEFAULT 'Direct',
                    stage TEXT NOT NULL DEFAULT 'New',
                    value REAL NOT NULL DEFAULT 0,
                    last_contacted TEXT,
                    next_followup TEXT,
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )

    def add_lead(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        email = str(payload.get("email", "")).strip().lower()
        if not name or "@" not in email:
            raise ValueError("A name and valid email are required.")
        stage = str(payload.get("stage", "New"))
        if stage not in STAGES:
            raise ValueError("Invalid pipeline stage.")
        created_at = datetime.now().replace(microsecond=0).isoformat()
        values = (
            name,
            str(payload.get("company", "")).strip(),
            email,
            str(payload.get("source", "Direct")).strip() or "Direct",
            stage,
            float(payload.get("value", 0) or 0),
            payload.get("last_contacted") or None,
            payload.get("next_followup") or None,
            str(payload.get("notes", "")).strip(),
            created_at,
        )
        try:
            with closing(self.connect()) as conn, conn:
                cursor = conn.execute(
                    """
                    INSERT INTO leads
                    (name, company, email, source, stage, value, last_contacted,
                     next_followup, notes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                lead_id = cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            raise ValueError("A lead with this email already exists.") from exc
        return self.get_lead(int(lead_id))

    def get_lead(self, lead_id: int) -> dict[str, Any]:
        with closing(self.connect()) as conn, conn:
            row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if row is None:
            raise KeyError("Lead not found.")
        return self._decorate(dict(row))

    def list_leads(self) -> list[dict[str, Any]]:
        with closing(self.connect()) as conn, conn:
            rows = conn.execute(
                """
                SELECT * FROM leads
                ORDER BY
                  CASE stage
                    WHEN 'Proposal' THEN 1 WHEN 'Qualified' THEN 2
                    WHEN 'Contacted' THEN 3 WHEN 'New' THEN 4
                    WHEN 'Won' THEN 5 ELSE 6 END,
                  COALESCE(next_followup, '9999-12-31'), created_at DESC
                """
            ).fetchall()
        return [self._decorate(dict(row)) for row in rows]

    def update_stage(self, lead_id: int, stage: str) -> dict[str, Any]:
        if stage not in STAGES:
            raise ValueError("Invalid pipeline stage.")
        with closing(self.connect()) as conn, conn:
            cursor = conn.execute("UPDATE leads SET stage = ? WHERE id = ?", (stage, lead_id))
            if cursor.rowcount == 0:
                raise KeyError("Lead not found.")
        return self.get_lead(lead_id)

    def dashboard(self) -> dict[str, Any]:
        leads = self.list_leads()
        open_leads = [lead for lead in leads if lead["stage"] not in {"Won", "Lost"}]
        pipeline_value = sum(float(lead["value"]) for lead in open_leads)
        won_value = sum(float(lead["value"]) for lead in leads if lead["stage"] == "Won")
        followups = sum(1 for lead in open_leads if lead["priority"] in {"High", "Medium"})
        stage_counts = {stage: 0 for stage in STAGES}
        for lead in leads:
            stage_counts[lead["stage"]] += 1
        return {
            "lead_count": len(leads),
            "open_count": len(open_leads),
            "pipeline_value": pipeline_value,
            "won_value": won_value,
            "followups_due": followups,
            "stage_counts": stage_counts,
            "leads": leads,
        }

    def seed_demo(self) -> None:
        if self.list_leads():
            return
        today = date.today()
        samples = [
            {
                "name": "Maya Chen",
                "company": "North Harbor Studio",
                "email": "maya@example.test",
                "source": "Website",
                "stage": "Qualified",
                "value": 2400,
                "last_contacted": str(today - timedelta(days=3)),
                "next_followup": str(today),
                "notes": "Needs a reusable intake and follow-up workflow.",
            },
            {
                "name": "Jordan Wells",
                "company": "Wells Supply Co.",
                "email": "jordan@example.test",
                "source": "Referral",
                "stage": "Proposal",
                "value": 5200,
                "last_contacted": str(today - timedelta(days=2)),
                "next_followup": str(today + timedelta(days=1)),
                "notes": "Proposal sent for inventory-alert automation.",
            },
            {
                "name": "Priya Shah",
                "company": "Saffron Wellness",
                "email": "priya@example.test",
                "source": "Email",
                "stage": "New",
                "value": 900,
                "next_followup": str(today),
                "notes": "Asked about consolidating customer inquiries.",
            },
            {
                "name": "Evan Brooks",
                "company": "Brooks Field Services",
                "email": "evan@example.test",
                "source": "Direct",
                "stage": "Won",
                "value": 1800,
                "last_contacted": str(today - timedelta(days=1)),
                "notes": "Kickoff complete.",
            },
        ]
        for sample in samples:
            self.add_lead(sample)

    @staticmethod
    def _decorate(lead: dict[str, Any]) -> dict[str, Any]:
        today = date.today()
        followup = lead.get("next_followup")
        if lead["stage"] in {"Won", "Lost"}:
            priority, action = "Closed", "No action required"
        elif followup and date.fromisoformat(followup) <= today:
            priority, action = "High", "Follow up today"
        elif lead["stage"] == "New":
            priority, action = "Medium", "Send a personal introduction"
        elif lead["stage"] == "Proposal":
            priority, action = "Medium", "Confirm proposal was received"
        else:
            priority, action = "Low", "Monitor the next scheduled step"
        lead["priority"] = priority
        lead["recommended_action"] = action
        return lead


class CRMHandler(BaseHTTPRequestHandler):
    store: CRMStore

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/dashboard":
            self._json(self.store.dashboard())
            return
        if path == "/api/leads":
            self._json(self.store.list_leads())
            return
        asset = "index.html" if path == "/" else path.lstrip("/")
        file_path = (STATIC / asset).resolve()
        if STATIC.resolve() not in file_path.parents or not file_path.is_file():
            self.send_error(404)
            return
        content_type = "text/html" if file_path.suffix == ".html" else "text/plain"
        if file_path.suffix == ".css":
            content_type = "text/css"
        elif file_path.suffix == ".js":
            content_type = "text/javascript"
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/leads":
            self.send_error(404)
            return
        try:
            self._json(self.store.add_lead(self._body()), 201)
        except (ValueError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, 400)

    def do_PATCH(self) -> None:
        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) != 4 or parts[:2] != ["api", "leads"] or parts[3] != "stage":
            self.send_error(404)
            return
        try:
            lead = self.store.update_stage(int(parts[2]), str(self._body().get("stage", "")))
            self._json(lead)
        except ValueError as exc:
            self._json({"error": str(exc)}, 400)
        except KeyError as exc:
            self._json({"error": str(exc)}, 404)


def serve(host: str = "127.0.0.1", port: int = 8765, db_path: str | Path = DEFAULT_DB) -> None:
    store = CRMStore(db_path)
    store.seed_demo()
    handler = type("ConfiguredCRMHandler", (CRMHandler,), {"store": store})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Business CRM Starter running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Business CRM Starter.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()
    serve(args.host, args.port, args.db)
