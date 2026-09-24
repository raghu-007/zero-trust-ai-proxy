"""Local-first FastAPI prototype with explicit authentication and audit boundaries."""
from contextlib import asynccontextmanager
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .config import Settings
from .core import ProxyError, RateLimiter, hash_api_key, parse_request
from .database import Store
from .middleware import read_bounded_body
from .service import AuditUnavailable, ExecutionService
from .tools import execute_tool

VERSION = "2.0.0"


def create_app(settings=None, store=None):
    settings = settings or Settings.from_environment()
    storage = store or Store(settings.database_url)
    service = ExecutionService(storage, execute_tool)
    limiter = RateLimiter(settings.rate_limit, settings.rate_window, settings.rate_clients)

    @asynccontextmanager
    async def lifespan(application):
        await run_in_threadpool(storage.initialize)
        try:
            yield
        finally:
            await run_in_threadpool(storage.close)

    app = FastAPI(
        title="AI Agent Proxy — local prototype", version=VERSION, lifespan=lifespan,
        docs_url="/docs" if settings.enable_docs else None, redoc_url=None,
        openapi_url="/openapi.json" if settings.enable_docs else None,
    )
    app.state.store = storage
    app.state.service = service
    app.state.limiter = limiter
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=list(settings.cors_origins),
            allow_credentials=False, allow_methods=["POST"],
            allow_headers=["Content-Type", "X-Agent-Key"],
            expose_headers=["X-Request-ID"],
        )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts),
                       www_redirect=False)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": VERSION, "mode": "mock"}

    @app.post("/execute", openapi_extra={
        "parameters": [{"name": "X-Agent-Key", "in": "header", "required": True,
                        "schema": {"type": "string"}}],
        "requestBody": {"required": True, "content": {"application/json": {
            "schema": {"type": "object", "additionalProperties": False,
                       "required": ["tool_name", "args"], "properties": {
                           "tool_name": {"type": "string", "enum": ["github_commit", "query_db"]},
                           "args": {"type": "object"}}},
            "example": {"tool_name": "github_commit", "args": {
                "repo": "demo/example", "message": "Example mock commit"}},
        }}},
    })
    async def execute(request: Request):
        request_id = uuid4().hex
        headers = {"X-Request-ID": request_id, "Cache-Control": "no-store"}
        try:
            await run_in_threadpool(storage.begin, request_id)
        except AuditUnavailable:
            return JSONResponse({"detail": "Audit storage unavailable"}, 503, headers=headers)
        result = None
        status_code, outcome, detail = 200, "succeeded", None
        try:
            peer = request.client.host if request.client else "unknown"
            if not limiter.allow(peer):
                raise ProxyError(429, "rate_limited", "Request limit reached")
            keys = request.headers.getlist("x-agent-key")
            if len(keys) != 1:
                raise ProxyError(401, "unauthenticated", "Invalid or missing credentials")
            hash_api_key(keys[0])
            body = await read_bounded_body(request, settings.body_timeout)
            tool_name, args = parse_request(body)
            result = await run_in_threadpool(service.run, request_id, keys[0], tool_name, args)
        except ProxyError as error:
            status_code, outcome, detail = error.status_code, error.outcome, error.message
        except AuditUnavailable:
            status_code, outcome, detail = 503, "storage_error", "Audit storage unavailable"
        except Exception:
            status_code, outcome, detail = 500, "internal_error", "Request could not be completed"
        try:
            await run_in_threadpool(storage.finish, request_id, outcome, status_code)
        except AuditUnavailable:
            # Authorized intent survives. A real connector may have already acted.
            # Automatic retry is unsafe without connector-specific idempotency.
            return JSONResponse({"detail": "Audit finalization unavailable"}, 503, headers=headers)
        if status_code == 429:
            headers["Retry-After"] = str(settings.rate_window)
        if status_code == 401:
            headers["WWW-Authenticate"] = "ApiKey"
        return JSONResponse(result if detail is None else {"detail": detail},
                            status_code, headers=headers)

    return app


app = create_app()
