"""Execution ordering and privacy policy, independent of the HTTP/ORM adapters."""

from .core import ProxyError, TOOLS, hash_api_key, redact_result, validate_arguments


class AuditUnavailable(Exception):
    pass


class ExecutionService:
    def __init__(self, store, execute):
        self.store = store
        self.execute = execute

    def run(self, request_id: str, api_key: str, tool_name: str, args: dict):
        digest = hash_api_key(api_key)
        agent_id = self.store.authenticate(digest)
        if agent_id is None:
            raise ProxyError(401, "unauthenticated", "Invalid or missing credentials")
        self.store.identify(request_id, agent_id, tool_name if tool_name in TOOLS else None)
        if tool_name not in TOOLS or not self.store.authorize(agent_id, tool_name):
            raise ProxyError(403, "denied", "Tool access denied")
        validated = validate_arguments(tool_name, args)
        # Persist permission and intent BEFORE calling a connector. Failure is closed.
        self.store.authorized(request_id, agent_id, tool_name)
        try:
            raw = self.execute(tool_name, validated)
            return redact_result(raw)
        except Exception:
            # Never persist or return exception strings from a connector.
            raise ProxyError(502, "tool_error", "Tool execution or output validation failed") from None
