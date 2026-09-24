import concurrent.futures
import json
import unittest
from app.core import (MAX_BODY_BYTES, ProxyError, RateLimiter, hash_api_key,
                      new_api_key, parse_request, redact_result, validate_arguments)


class CredentialTests(unittest.TestCase):
    def test_generated_keys_and_digests(self):
        keys = {new_api_key() for _ in range(50)}
        self.assertEqual(len(keys), 50)
        self.assertTrue(all(len(k) == 47 and len(hash_api_key(k)) == 64 for k in keys))
        key = keys.pop()
        self.assertEqual(hash_api_key(key), hash_api_key(key))
        self.assertNotIn(key, hash_api_key(key))

    def test_legacy_malformed_and_missing_keys_rejected(self):
        for key in (None, "", "sk-mock-key-123", "ztp_short", "x" * 100000,
                    "ztp_" + "é" * 43, new_api_key() + "\n"):
            with self.subTest(length=len(key) if key else 0), self.assertRaises(ProxyError) as caught:
                hash_api_key(key)
            self.assertEqual(caught.exception.status_code, 401)


class RequestTests(unittest.TestCase):
    def test_valid_tool_request(self):
        payload = {"tool_name": "github_commit", "args": {"repo": "demo/example", "message": "Example"}}
        name, args = parse_request(json.dumps(payload).encode())
        self.assertEqual(validate_arguments(name, args), payload["args"])

    def test_duplicate_json_and_nonfinite_values_rejected(self):
        for body in (b'{"tool_name":"github_commit","args":{},"args":{}}',
                     b'{"tool_name":"github_commit","args":{"message":NaN}}',
                     b'\xff', b'{"secret":"do-not-echo"', b'[' * 1500 + b']' * 1500):
            with self.subTest(body=body[:12]), self.assertRaises(ProxyError) as caught:
                parse_request(body)
            self.assertEqual(caught.exception.status_code, 400)
            self.assertNotIn("do-not-echo", str(caught.exception))

    def test_request_shape_and_unknown_tools(self):
        for value in ([], None, {}, {"tool_name": "drop_table", "args": {}},
                      {"tool_name": "github_commit", "args": [], "extra": 1}):
            with self.subTest(value=value), self.assertRaises(ProxyError):
                parse_request(json.dumps(value).encode())

    def test_body_limit(self):
        with self.assertRaises(ProxyError) as caught:
            parse_request(b" " * (MAX_BODY_BYTES + 1))
        self.assertEqual(caught.exception.status_code, 413)

    def test_argument_schema(self):
        for args in ({"repo": "demo/example", "message": "ok", "token": "extra"},
                     {"repo": "../example", "message": "x"},
                     {"repo": "demo/example", "message": "\n"},
                     {"repo": "demo/example", "message": "x" * 513},
                     {"repo": True, "message": "x"}, {"repo": "demo/example"}):
            with self.subTest(args=args), self.assertRaises(ProxyError):
                validate_arguments("github_commit", args)
        self.assertEqual(validate_arguments("query_db", {"query": "SELECT * FROM demo_users"}),
                         {"query": "SELECT * FROM demo_users"})
        with self.assertRaises(ProxyError):
            validate_arguments("query_db", {"query": "DROP TABLE users"})


class RedactionTests(unittest.TestCase):
    def test_structured_fields_including_numeric_sensitive_values(self):
        result = redact_result({"results": [{"id": 1, "name": "Example", "email": "x@example.test",
                                            "card_number": 4111111111111111}], "ok": True})
        self.assertEqual(result["results"][0], {"id": 1, "name": "[REDACTED]",
                                               "email": "[REDACTED]", "card_number": "[REDACTED]"})
        self.assertEqual(json.loads(json.dumps(result)), result)

    def test_card_does_not_leave_prefix_after_phone_redaction(self):
        result = redact_result({"value": "card 4111111111111111"})
        self.assertEqual(result["value"], "card [REDACTED_NUMBER]")

    def test_numeric_result_remains_valid_json(self):
        result = redact_result({"reference": 4111111111111111, "count": 3, "value": None})
        self.assertEqual(json.loads(json.dumps(result))["reference"], "[REDACTED_NUMBER]")
        self.assertEqual(result["count"], 3)

    def test_text_email_phone_ssn_ip_and_token(self):
        examples = ["alice@example.test", "+91 98765 43210", "123-45-6789",
                    "192.0.2.10", "2001:db8::1", new_api_key()]
        for value in examples:
            with self.subTest(value=value[:5]):
                output = redact_result({"value": value})["value"]
                self.assertNotIn(value, output)
                self.assertIn("REDACTED", output)

    def test_sensitive_subtrees_removed(self):
        self.assertEqual(redact_result({"access_token": {"nested": "credential"}}),
                         {"access_token": "[REDACTED]"})

    def test_invalid_outputs_fail_closed(self):
        deep = "x"
        for _ in range(12): deep = [deep]
        for value in (float("nan"), float("inf"), object(), {"bad-key": "x"},
                      "x" * 4097, "\ud800", list(range(2001)), deep):
            with self.subTest(kind=type(value)), self.assertRaises(ValueError):
                redact_result(value)

    def test_aggregate_output_size_bound(self):
        with self.assertRaises(ValueError):
            redact_result(["x" * 4000] * 10)

    def test_input_is_not_mutated(self):
        original = {"email": "alice@example.test", "nested": [1, 2]}
        redact_result(original)
        self.assertEqual(original["email"], "alice@example.test")


class RateLimitTests(unittest.TestCase):
    def test_exact_window_boundary(self):
        now = [0]
        limiter = RateLimiter(2, 60, 2, lambda: now[0])
        self.assertTrue(limiter.allow("a"))
        self.assertTrue(limiter.allow("a"))
        self.assertFalse(limiter.allow("a"))
        now[0] = 59.999
        self.assertFalse(limiter.allow("a"))
        now[0] = 60
        self.assertTrue(limiter.allow("a"))

    def test_full_capacity_does_not_evict_active_client(self):
        now = [0]
        limiter = RateLimiter(1, 60, 1, lambda: now[0])
        self.assertTrue(limiter.allow("a"))
        self.assertFalse(limiter.allow("b"))
        self.assertFalse(limiter.allow("a"))
        now[0] = 60
        self.assertTrue(limiter.allow("b"))
        self.assertEqual(len(limiter._clients), 1)

    def test_check_and_consume_is_atomic(self):
        limiter = RateLimiter(5, 60, 1)
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            outcomes = list(pool.map(lambda _: limiter.allow("one"), range(50)))
        self.assertEqual(sum(outcomes), 5)

    def test_rejected_requests_do_not_grow_state(self):
        limiter = RateLimiter(1, 60, 1)
        limiter.allow("one")
        for _ in range(100): limiter.allow("one")
        self.assertEqual(len(limiter._clients["one"]), 1)


if __name__ == "__main__":
    unittest.main()
