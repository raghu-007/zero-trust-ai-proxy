"""
Rate limiting middleware for the Zero-Trust AI Agent Proxy.

Uses a simple in-memory sliding window approach per client IP.
For production, replace with Redis-backed rate limiting (e.g., slowapi + redis).
"""

import time
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple in-memory sliding-window rate limiter.

    Args:
        app: The ASGI application.
        max_requests: Maximum number of requests allowed per window.
        window_seconds: Time window in seconds.
    """

    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # { client_ip: [timestamp1, timestamp2, ...] }
        self._request_log: dict[str, list[float]] = defaultdict(list)

    def _clean_old_requests(self, client_ip: str, now: float):
        """Remove timestamps older than the current window."""
        cutoff = now - self.window_seconds
        self._request_log[client_ip] = [
            ts for ts in self._request_log[client_ip] if ts > cutoff
        ]

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path == "/health":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        self._clean_old_requests(client_ip, now)

        if len(self._request_log[client_ip]) >= self.max_requests:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded. Max {self.max_requests} requests per {self.window_seconds}s."
                },
            )

        self._request_log[client_ip].append(now)
        return await call_next(request)
