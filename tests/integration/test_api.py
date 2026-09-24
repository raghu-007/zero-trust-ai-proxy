"""Requires requirements-dev.txt; never silently skipped if dependencies are absent."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.config import Settings
from app.core import RateLimiter, new_api_key
from app.database import Store
from app.main import create_app
from app.models import Agent, AuditEvent, AuditLog, Policy
from app.service import AuditUnavailable
from init_db import provision


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = Settings(database_url="sqlite:///" + (self.root / "test.db").as_posix(),
                                 allowed_hosts=("testserver",))
        self.store = Store(self.settings.database_url)
        self.key_file = self.root / "agent.key"
        provision(self.store, "Test-Bot", self.key_file)
        self.key = self.key_file.read_text().strip()
        self.app = create_app(self.settings, self.store)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def request(self, key=None, payload=None):
        return self.client.post("/execute", headers={"X-Agent-Key": self.key if key is None else key},
                                json=payload or {"tool_name": "github_commit", "args": {
                                    "repo": "demo/example", "message": "private-input"}})

    def events(self):
        with self.store.sessions() as session:
            return session.scalars(select(AuditEvent).order_by(AuditEvent.created_at)).all()

    def test_authorized_request_and_metadata_audit(self):
        response = self.request()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "mock_success")
        self.assertNotIn("private-input", response.text)
        event = self.events()[0]
        self.assertEqual(event.request_id, response.headers["x-request-id"])
        self.assertEqual((event.outcome, event.status_code, event.tool_name),
                         ("succeeded", 200, "github_commit"))
        self.assertIsNotNone(event.agent_id)
        self.assertFalse(hasattr(event, "arguments"))
        self.assertFalse(hasattr(event, "execution_result"))
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_missing_invalid_legacy_and_duplicate_keys(self):
        responses = [self.client.post("/execute", json={}), self.request("sk-mock-key-123"),
                     self.request(new_api_key()), self.client.post("/execute", json={},
                         headers=[("X-Agent-Key", self.key), ("X-Agent-Key", self.key)])]
        self.assertEqual([r.status_code for r in responses], [401] * 4)
        self.assertEqual([e.outcome for e in self.events()], ["unauthenticated"] * 4)

    def test_deactivated_agent_rejected(self):
        with self.store.sessions.begin() as session:
            session.scalar(select(Agent)).is_active = False
        self.assertEqual(self.request().status_code, 401)

    def test_denied_tool_not_executed(self):
        with patch.object(self.app.state.service, "execute") as connector:
            response = self.request(payload={"tool_name": "query_db", "args": {"query": "SELECT * FROM demo_users"}})
        self.assertEqual(response.status_code, 403)
        connector.assert_not_called()
        self.assertEqual(self.events()[0].outcome, "denied")

    def test_explicit_deny_wins_over_duplicate_allow(self):
        with self.store.sessions.begin() as session:
            agent_id = session.scalar(select(Agent.id))
            session.add(Policy(agent_id=agent_id, tool_name="github_commit", is_allowed=False))
        self.assertEqual(self.request().status_code, 403)

    def test_query_demo_redacts_structured_fields(self):
        with self.store.sessions.begin() as session:
            agent_id = session.scalar(select(Agent.id))
            session.execute(delete(Policy).where(Policy.tool_name == "query_db"))
            session.add(Policy(agent_id=agent_id, tool_name="query_db", is_allowed=True))
        response = self.request(payload={"tool_name": "query_db", "args": {"query": "SELECT * FROM demo_users"}})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["results"][0], {
            "id": 1, "name": "[REDACTED]", "email": "[REDACTED]", "ssn": "[REDACTED]"})

    def test_bad_json_schema_and_oversized_body_are_audited(self):
        headers = {"X-Agent-Key": self.key, "Content-Type": "application/json"}
        first = self.client.post("/execute", headers=headers, content=b"not JSON private-data")
        second = self.request(payload={"tool_name": "unknown", "args": {}})
        third = self.client.post("/execute", headers=headers, content=b"x" * 32769)
        self.assertEqual([first.status_code, second.status_code, third.status_code], [400, 422, 413])
        self.assertNotIn("private-data", first.text)
        self.assertEqual(len(self.events()), 3)

    def test_rate_rejection_is_audited(self):
        self.app.state.limiter.limit = 1
        self.assertEqual(self.request().status_code, 200)
        response = self.request()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["retry-after"], "60")
        self.assertEqual(self.events()[-1].outcome, "rate_limited")

    def test_audit_failure_prevents_connector(self):
        for method in ("begin", "authorized"):
            with self.subTest(method=method), patch.object(self.store, method, side_effect=AuditUnavailable), \
                    patch.object(self.app.state.service, "execute") as connector:
                response = self.request()
                self.assertEqual(response.status_code, 503)
                connector.assert_not_called()

    def test_finalization_failure_retains_intent_and_returns_no_result(self):
        with patch.object(self.store, "finish", side_effect=AuditUnavailable), \
                patch.object(self.app.state.service, "execute", return_value={"private": "result"}) as connector:
            response = self.request()
        self.assertEqual(response.status_code, 503)
        connector.assert_called_once()
        self.assertNotIn("private", response.text)
        self.assertEqual(self.events()[0].outcome, "authorized")

    def test_connector_errors_are_sanitized(self):
        with patch.object(self.app.state.service, "execute", side_effect=RuntimeError("token=private-value")):
            response = self.request()
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private-value", response.text)
        self.assertEqual(self.events()[0].outcome, "tool_error")

    def test_host_guard_and_docs_defaults(self):
        self.assertEqual(self.client.get("/health", headers={"Host": "untrusted.example"}).status_code, 400)
        self.assertEqual(self.client.get("/docs").status_code, 404)
        self.assertEqual(self.client.get("/health").json()["mode"], "mock")

    def test_explicit_cors_allowlist(self):
        settings = Settings(database_url=self.settings.database_url, allowed_hosts=("testserver",),
                            cors_origins=("https://frontend.example.test",))
        with TestClient(create_app(settings)) as client:
            headers = {"Origin": "https://frontend.example.test", "Access-Control-Request-Method": "POST",
                       "Access-Control-Request-Headers": "X-Agent-Key,Content-Type"}
            allowed = client.options("/execute", headers=headers)
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(allowed.headers["access-control-allow-origin"], headers["Origin"])
            self.assertNotIn("access-control-allow-credentials", allowed.headers)
            headers["Origin"] = "https://untrusted.example"
            self.assertEqual(client.options("/execute", headers=headers).status_code, 400)

    def test_rotation_invalidates_old_key(self):
        new_file = self.root / "rotated.key"
        provision(self.store, "Test-Bot", new_file, rotate=True)
        self.assertEqual(self.request(self.key).status_code, 401)
        self.assertEqual(self.request(new_file.read_text().strip()).status_code, 200)

    def test_provision_never_overwrites_existing_file(self):
        before = self.key_file.read_bytes()
        with self.assertRaises(FileExistsError):
            provision(self.store, "Another-Bot", self.key_file)
        self.assertEqual(before, self.key_file.read_bytes())
        with self.store.sessions() as session:
            self.assertIsNone(session.scalar(select(Agent).where(Agent.name == "Another-Bot")))
        if os.name == "posix":
            self.assertEqual(self.key_file.stat().st_mode & 0o777, 0o600)

    def test_legacy_audits_are_not_silently_deleted(self):
        with self.store.sessions.begin() as session:
            session.add(AuditLog(arguments="legacy-private-data"))
        self.assertEqual(self.request().status_code, 200)
        with self.store.sessions() as session:
            self.assertEqual(session.scalar(select(AuditLog.arguments)), "legacy-private-data")


if __name__ == "__main__": unittest.main()
