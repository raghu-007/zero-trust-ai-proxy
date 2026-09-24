"""Bounded HTTP request intake."""
import asyncio
import re
from .core import MAX_BODY_BYTES, ProxyError


async def read_bounded_body(request, timeout):
    for name in ("content-length", "content-type", "content-encoding"):
        if len(request.headers.getlist(name)) > 1:
            raise ProxyError(400, "invalid_request", "Duplicate content headers")
    if request.headers.get("content-encoding", "identity").lower() != "identity":
        raise ProxyError(415, "invalid_request", "Compressed request bodies are not supported")
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise ProxyError(415, "invalid_request", "Content-Type must be application/json")
    length = request.headers.get("content-length")
    if length is not None:
        if not re.fullmatch(r"[0-9]{1,10}", length):
            raise ProxyError(400, "invalid_request", "Invalid Content-Length")
        if int(length) > MAX_BODY_BYTES:
            raise ProxyError(413, "rejected", "Request body is too large")
    body = bytearray()
    try:
        async with asyncio.timeout(timeout):
            async for chunk in request.stream():
                if len(body) + len(chunk) > MAX_BODY_BYTES:
                    raise ProxyError(413, "rejected", "Request body is too large")
                body.extend(chunk)
    except TimeoutError:
        raise ProxyError(408, "rejected", "Request body timed out") from None
    if length is not None and len(body) != int(length):
        raise ProxyError(400, "invalid_request", "Content-Length does not match body")
    return bytes(body)
