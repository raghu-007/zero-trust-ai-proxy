# Architecture and limits

The HTTP adapter in [app/main.py](../app/main.py) applies local defaults and turns
internal errors into controlled responses. [app/middleware.py](../app/middleware.py)
bounds incoming bytes and read time. [app/core.py](../app/core.py) contains the
dependency-free credential, schema, redaction, and rate-limit boundaries.

[app/service.py](../app/service.py) authenticates the digest, records the identified
agent, checks tool permissions, validates arguments, persists authorized intent,
and invokes an allowlisted connector. [app/database.py](../app/database.py) is the
SQLAlchemy adapter. [app/tools.py](../app/tools.py) contains only mock connectors.

## Trust boundaries

- Agent keys are uniformly random credentials, not user-selected passwords.
  SHA-256 storage is intended for these high-entropy tokens.
- A valid key grants only configured tool access. It is not evidence of a human
  approving a particular operation.
- Tool arguments are untrusted. The mock registry is fixed in code; the client
  cannot supply a module path, executable, callback URL, or function name outside
  that registry.
- Audit data is deliberately minimal. It records decisions, not a verbatim
  transcript of potentially sensitive inputs and outputs.
- Structured redaction avoids modifying serialized JSON syntax. It is not a
  guarantee that every secret, name, international format, encoded value, or
  indirect identifier will be detected.
- CORS controls browser response access; it does not replace authentication.
  Host validation does not replace TLS or an authenticated ingress.

## Resource and failure behavior

The limiter uses a lock, monotonic time, and bounded per-client queues. It removes
expired buckets and rejects new clients at capacity rather than evicting active
limits. It is per process and resets on restart. It is not a distributed quota;
a shared proxy or NAT may place many users in one bucket.

The supplied Uvicorn command ignores forwarded headers. A real ingress needs
explicit trusted-proxy configuration and limits before requests reach the app.
The body deadline is not a connector execution deadline.

Audits are synchronous and execution intent must persist before a tool runs.
If finalization fails afterwards, the request returns 503 while the authorized
intent remains. This is not transactional exactly-once execution. A real
connector needs idempotency and reconciliation before automatic retries.

Audit storage grows with attempts, including denied requests. No retention worker
is included. A real deployment needs storage limits, retention, ingress abuse
controls, and alerts for storage failure.

## Work still required for real connectors

- Resource-level policy: specific repositories, databases, operations, and tenants.
- Short-lived identities, revocation operations, and key-lifecycle administration.
- Connector-specific deadlines, cancellation, isolation, output schemas, and egress restrictions.
- Human approval and idempotency for consequential operations.
- TLS termination, trusted ingress, secrets management, and an operational threat model.
- Durable policy/audit operations, reviewed schema migrations, and retention.
- Evaluation of redaction against representative data and a suitable data-release policy.

Adding a prompt-injection keyword filter would not provide these controls.
The repository intentionally makes no claim of preventing all prompt injection
or of being an enterprise-ready zero-trust platform.
