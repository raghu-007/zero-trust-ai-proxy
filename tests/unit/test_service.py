import unittest
from unittest.mock import Mock
from app.core import ProxyError, hash_api_key, new_api_key
from app.service import AuditUnavailable, ExecutionService


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.key = new_api_key()
        self.store = Mock()
        self.store.authenticate.return_value = 7
        self.store.authorize.return_value = True
        self.connector = Mock(return_value={"status": "ok"})
        self.service = ExecutionService(self.store, self.connector)
        self.args = {"repo": "demo/example", "message": "private-argument"}

    def run_request(self):
        return self.service.run("request-id", self.key, "github_commit", self.args)

    def test_permission_and_durable_intent_precede_connector(self):
        order = []
        self.store.authorize.side_effect = lambda *_: order.append("permission") or True
        self.store.authorized.side_effect = lambda *_: order.append("intent")
        self.connector.side_effect = lambda *_: order.append("connector") or {"id": 1}
        self.assertEqual(self.run_request(), {"id": 1})
        self.assertEqual(order, ["permission", "intent", "connector"])
        self.store.authenticate.assert_called_once_with(hash_api_key(self.key))

    def test_unknown_key_never_executes(self):
        self.store.authenticate.return_value = None
        with self.assertRaises(ProxyError) as error: self.run_request()
        self.assertEqual(error.exception.status_code, 401)
        self.connector.assert_not_called()

    def test_denied_policy_never_executes(self):
        self.store.authorize.return_value = False
        with self.assertRaises(ProxyError) as error: self.run_request()
        self.assertEqual(error.exception.status_code, 403)
        self.connector.assert_not_called()

    def test_invalid_arguments_never_execute(self):
        self.args["extra"] = "should-not-be-accepted"
        with self.assertRaises(ProxyError): self.run_request()
        self.connector.assert_not_called()

    def test_unavailable_audit_blocks_execution(self):
        self.store.authorized.side_effect = AuditUnavailable
        with self.assertRaises(AuditUnavailable): self.run_request()
        self.connector.assert_not_called()

    def test_connector_exception_does_not_echo_sensitive_message(self):
        self.connector.side_effect = RuntimeError("password=private-value")
        with self.assertRaises(ProxyError) as error: self.run_request()
        self.assertEqual(error.exception.status_code, 502)
        self.assertNotIn("private-value", str(error.exception))

    def test_invalid_result_does_not_escape(self):
        self.connector.return_value = {"data": object()}
        with self.assertRaises(ProxyError) as error: self.run_request()
        self.assertEqual(error.exception.status_code, 502)

    def test_audit_receives_metadata_only(self):
        self.connector.return_value = {"email": "private@example.test"}
        self.assertEqual(self.run_request(), {"email": "[REDACTED]"})
        calls = str(self.store.mock_calls)
        for value in (self.key, "private-argument", "private@example.test"):
            self.assertNotIn(value, calls)


if __name__ == "__main__":
    unittest.main()
