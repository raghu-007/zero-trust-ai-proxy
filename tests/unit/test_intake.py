import asyncio
import unittest
from unittest.mock import patch
from app.config import Settings
from app.core import MAX_BODY_BYTES, ProxyError
from app.middleware import read_bounded_body


class Headers:
    def __init__(self, pairs): self.pairs = [(k.lower(), v) for k, v in pairs]
    def getlist(self, name): return [v for k, v in self.pairs if k == name.lower()]
    def get(self, name, default=None):
        values = self.getlist(name)
        return values[-1] if values else default


class Request:
    def __init__(self, chunks, extra=(), delay=0):
        self.headers = Headers([("content-type", "application/json"), *extra])
        self.chunks, self.delay = chunks, delay
    async def stream(self):
        for chunk in self.chunks:
            if self.delay: await asyncio.sleep(self.delay)
            yield chunk


class IntakeTests(unittest.IsolatedAsyncioTestCase):
    async def test_bounded_chunks_are_combined(self):
        request = Request([b"{", b"}"], [("content-length", "2")])
        self.assertEqual(await read_bounded_body(request, 1), b"{}")

    async def test_actual_size_checked_without_length_header(self):
        with self.assertRaises(ProxyError) as error:
            await read_bounded_body(Request([b"x" * MAX_BODY_BYTES, b"x"]), 1)
        self.assertEqual(error.exception.status_code, 413)

    async def test_untrusted_length_headers(self):
        for pairs, code in (([("content-length", "999999")], 413),
                            ([("content-length", "-1")], 400),
                            ([("content-length", "1"), ("content-length", "1")], 400),
                            ([("content-length", "3")], 400)):
            with self.subTest(pairs=pairs), self.assertRaises(ProxyError) as error:
                await read_bounded_body(Request([b"{}"], pairs), 1)
            self.assertEqual(error.exception.status_code, code)

    async def test_encoding_and_duplicate_type_rejected(self):
        for pairs in ([("content-encoding", "gzip")], [("content-type", "text/plain")]):
            with self.subTest(pairs=pairs), self.assertRaises(ProxyError):
                await read_bounded_body(Request([b"{}"], pairs), 1)

    async def test_slow_body_times_out(self):
        with self.assertRaises(ProxyError) as error:
            await read_bounded_body(Request([b"{}"], delay=1), 0.01)
        self.assertEqual(error.exception.status_code, 408)


class ConfigurationTests(unittest.TestCase):
    def test_local_defaults_and_explicit_origins(self):
        defaults = Settings()
        self.assertEqual(defaults.cors_origins, ())
        self.assertFalse(defaults.enable_docs)
        self.assertNotIn("*", defaults.allowed_hosts)
        Settings(cors_origins=("http://localhost:5173", "https://example.test"))

    def test_rejects_wildcards_credentials_and_paths(self):
        for origin in ("*", "https://*.example.test", "https://user:password@example.test",
                       "https://example.test/", "https://example.test/path", "file:///tmp",
                       "https://example.test:bad", " https://example.test", "https://exam ple.test"):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                Settings(cors_origins=(origin,))

    def test_bounds_and_host_controls(self):
        for options in ({"rate_limit": 0}, {"rate_window": -1}, {"rate_clients": 10001},
                        {"body_timeout": 100}, {"allowed_hosts": ("*",)},
                        {"database_url": "postgresql://unconfigured"}):
            with self.subTest(options=options), self.assertRaises(ValueError): Settings(**options)

    def test_environment_settings(self):
        with patch.dict("os.environ", {"ZT_ENABLE_DOCS": "true", "ZT_RATE_LIMIT": "5"}, clear=True):
            settings = Settings.from_environment()
        self.assertTrue(settings.enable_docs)
        self.assertEqual(settings.rate_limit, 5)


if __name__ == "__main__": unittest.main()
