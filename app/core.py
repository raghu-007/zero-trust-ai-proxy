"""Dependency-free security boundaries shared by the API and regression tests."""

from __future__ import annotations

from collections import OrderedDict, deque
import hashlib
import ipaddress
import json
import math
import re
import secrets
from threading import Lock
import time


KEY_PATTERN = re.compile(r"ztp_[A-Za-z0-9_-]{43}", re.ASCII)
TOOLS = frozenset({"github_commit", "query_db"})
MAX_BODY_BYTES = 32_768
MAX_RESULT_BYTES = 32_768


class ProxyError(Exception):
    def __init__(self, status_code: int, outcome: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.outcome = outcome
        self.message = message


def new_api_key() -> str:
    return "ztp_" + secrets.token_urlsafe(32)


def hash_api_key(value: str) -> str:
    if type(value) is not str or not KEY_PATTERN.fullmatch(value):
        raise ProxyError(401, "unauthenticated", "Invalid or missing credentials")
    # Appropriate for uniformly random 256-bit credentials, not user passwords.
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("nonfinite JSON number")


def parse_request(body: bytes) -> tuple[str, dict]:
    if len(body) > MAX_BODY_BYTES:
        raise ProxyError(413, "rejected", "Request body is too large")
    try:
        obj = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object,
                         parse_constant=_reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise ProxyError(400, "invalid_request", "Expected unambiguous UTF-8 JSON") from None
    pending = [(obj, 0)]
    visited = 0
    while pending:
        item, depth = pending.pop()
        visited += 1
        if depth > 10 or visited > 2000 or (type(item) is float and not math.isfinite(item)):
            raise ProxyError(400, "invalid_request", "JSON structure exceeds supported limits")
        if type(item) is dict:
            pending.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)
    if (
        type(obj) is not dict or set(obj) != {"tool_name", "args"}
        or type(obj["tool_name"]) is not str or obj["tool_name"] not in TOOLS
        or type(obj["args"]) is not dict
    ):
        raise ProxyError(422, "invalid_request", "Unknown tool or invalid request structure")
    return obj["tool_name"], obj["args"]


def validate_arguments(tool_name: str, args: dict) -> dict:
    valid = False
    if tool_name == "github_commit" and set(args) == {"repo", "message"}:
        repo, message = args["repo"], args["message"]
        valid = (
            type(repo) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", repo)
            and all(part not in {".", ".."} for part in repo.split("/"))
            and type(message) is str and 1 <= len(message) <= 512
            and bool(message.strip()) and not any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in message)
        )
    elif tool_name == "query_db" and set(args) == {"query"}:
        # This is a fixed demo dataset, not an SQL execution facility.
        valid = args["query"] == "SELECT * FROM demo_users" and type(args["query"]) is str
    if not valid:
        raise ProxyError(422, "invalid_request", "Arguments do not match the tool contract")
    return dict(args)


SENSITIVE_FIELDS = frozenset({
    "name", "fullname", "email", "ssn", "phone", "phonenumber", "mobile",
    "creditcard", "cardnumber", "password", "secret", "token", "accesstoken",
    "apikey", "authorization", "cookie", "setcookie", "address", "ip", "ipaddress",
})
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
PHONE = re.compile(r"(?<!\w)(?:\+\d{1,3}[ .-]?)?\(?\d{2,5}\)?(?:[ .-]?\d){7,12}(?!\d)")
IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
IPV6 = re.compile(r"(?<![\w:])[0-9A-Fa-f:]{2,45}(?![\w:])")
TOKEN = re.compile(r"\b(?:ztp_[A-Za-z0-9_-]{43}|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{16,})\b")


def redact_text(text: str) -> str:
    text = TOKEN.sub("[REDACTED_TOKEN]", text)
    text = EMAIL.sub("[REDACTED_EMAIL]", text)
    text = SSN.sub("[REDACTED_SSN]", text)
    # Cards must precede phone matching; otherwise their suffix can be consumed.
    text = CARD.sub("[REDACTED_NUMBER]", text)
    text = PHONE.sub("[REDACTED_PHONE]", text)
    text = IPV4.sub("[REDACTED_IP]", text)

    def ipv6(match):
        candidate = match.group()
        if ":" not in candidate:
            return candidate
        try:
            ipaddress.IPv6Address(candidate)
            return "[REDACTED_IP]"
        except ValueError:
            return candidate

    return IPV6.sub(ipv6, text)


def redact_result(value):
    """Conservative JSON-value redaction, not a complete data-loss prevention system."""
    remaining = [2000]

    def walk(item, depth=0):
        remaining[0] -= 1
        if depth > 10 or remaining[0] < 0:
            raise ValueError("result structure exceeds limits")
        if item is None or type(item) is bool:
            return item
        if type(item) is int:
            return "[REDACTED_NUMBER]" if abs(item) >= 1_000_000_000 else item
        if type(item) is float:
            if not math.isfinite(item):
                raise ValueError("nonfinite result")
            return "[REDACTED_NUMBER]" if abs(item) >= 1_000_000_000 else item
        if type(item) is str:
            if len(item) > 4096 or any(0xD800 <= ord(c) <= 0xDFFF for c in item):
                raise ValueError("invalid result string")
            return redact_text(item)
        if type(item) is list:
            return [walk(child, depth + 1) for child in item]
        if type(item) is dict:
            output = {}
            for key, child in item.items():
                if type(key) is not str or len(key) > 64 or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                    raise ValueError("result keys must be schema field names")
                normalized = key.replace("_", "").lower()
                output[key] = "[REDACTED]" if normalized in SENSITIVE_FIELDS else walk(child, depth + 1)
            return output
        raise ValueError("unsupported result type")

    output = walk(value)
    encoded = json.dumps(output, ensure_ascii=True, allow_nan=False)
    if len(encoded.encode("ascii")) > MAX_RESULT_BYTES:
        raise ValueError("result exceeds limits")
    return output


class RateLimiter:
    """Bounded per-process sliding window; full capacity rejects new identities."""

    def __init__(self, limit=60, window=60, max_clients=1024, clock=time.monotonic):
        if any(type(v) is not int or v <= 0 for v in (limit, window, max_clients)):
            raise ValueError("invalid rate-limit configuration")
        self.limit, self.window, self.max_clients = limit, window, max_clients
        self.clock = clock
        self._clients = OrderedDict()
        self._lock = Lock()

    def allow(self, identity: str) -> bool:
        with self._lock:
            now = self.clock()
            # Ordered by last accepted request; remove completely expired buckets.
            while self._clients:
                oldest, queue = next(iter(self._clients.items()))
                if now - queue[-1] < self.window:
                    break
                del self._clients[oldest]
            queue = self._clients.get(identity)
            if queue is None:
                if len(self._clients) >= self.max_clients:
                    return False
                queue = self._clients[identity] = deque()
            while queue and now - queue[0] >= self.window:
                queue.popleft()
            if len(queue) >= self.limit:
                return False
            queue.append(now)
            self._clients.move_to_end(identity)
            return True
