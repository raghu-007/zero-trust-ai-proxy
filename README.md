# Zero-Trust AI Agent Control Plane

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com)

A secure, enterprise-grade proxy layer for AI Agents (like LangChain, AutoGPT, or custom bots).

## The Problem
When deploying AI agents into an enterprise environment, they need access to internal APIs, databases, and infrastructure to be useful. However, giving an LLM direct access to these tools is a massive security risk (Prompt Injection, Data Exfiltration, Accidental Deletion).

## The Solution
This project acts as an **FDE (Forward Deployed Engineering) Control Plane**. The AI agent never executes tools directly. Instead, it sends a request to this proxy.

### How It Works

```
AI Agent                    Zero-Trust Proxy                    Internal Tools
   │                              │                                   │
   │── POST /execute ────────────>│                                   │
   │   (X-Agent-Key header)       │                                   │
   │                              │── 1. Authenticate (hash & lookup) │
   │                              │── 2. Check RBAC policy ──────────>│
   │                              │── 3. Rate limit check             │
   │                              │── 4. Execute tool ───────────────>│
   │                              │<── Raw result ────────────────────│
   │                              │── 5. Redact PII (email, SSN,      │
   │                              │      phone, CC, IP)               │
   │                              │── 6. Log audit trail              │
   │<── Safe, redacted response──│                                   │
```

### Key Features
*   **Role-Based Access Control (RBAC):** Just because an agent wants to run `drop_table`, doesn't mean it can. The proxy checks a database to see if that specific agent is authorized for that specific tool.
*   **API Key Hashing:** Agent API keys are stored as SHA-256 hashes — never in plain text.
*   **Rate Limiting:** Per-IP sliding window rate limiter (60 req/min default) prevents abuse.
*   **Audit Logging:** Every single execution attempt (allowed or blocked) is logged to the database with timestamps, arguments, and the exact result. Ready for SIEM ingestion (Datadog/Splunk).
*   **PII Redaction:** Before returning query results to the agent, the proxy automatically scrubs Personally Identifiable Information (emails, SSNs, phone numbers, credit cards, IP addresses) so they don't leak back to external LLM providers (OpenAI/Anthropic).
*   **CORS Support:** Pre-configured for frontend integration.

## Project Structure
```
zero-trust-ai-proxy/
├── app/
│   ├── __init__.py       # Package init
│   ├── main.py           # FastAPI app, /execute & /health endpoints
│   ├── models.py         # SQLAlchemy models (Agent, Policy, AuditLog)
│   ├── database.py       # DB engine & session config
│   ├── security.py       # Auth, RBAC, API key hashing, PII redaction
│   ├── middleware.py      # Rate limiting middleware
│   └── tools.py          # Mock tool registry
├── init_db.py            # Seeds DB with mock agent & policies
├── requirements.txt      # Python dependencies
├── Dockerfile            # Container build
├── docker-compose.yml    # Docker orchestration
└── README.md
```

## Getting Started

### 1. Setup
```bash
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Initialize Database (Mock Data)
```bash
python init_db.py
```
*This creates an agent named 'DevOps-Bot' with the API Key 'sk-mock-key-123' (stored as a SHA-256 hash) and gives it permission to run 'github_commit' but NOT 'query_db'.*

### 3. Run the Server
```bash
# Locally
uvicorn app.main:app --reload

# Or via Docker
docker-compose up --build
```

### 4. Test it!

**Authorized Request (Will Succeed):**
```bash
curl -X POST "http://127.0.0.1:8000/execute" \
     -H "X-Agent-Key: sk-mock-key-123" \
     -H "Content-Type: application/json" \
     -d '{"tool_name": "github_commit", "args": {"repo": "internal-frontend", "message": "fix bug"}}'
```

**Unauthorized Request (Will be Blocked & Logged):**
```bash
curl -X POST "http://127.0.0.1:8000/execute" \
     -H "X-Agent-Key: sk-mock-key-123" \
     -H "Content-Type: application/json" \
     -d '{"tool_name": "query_db", "args": {"query": "SELECT * FROM users"}}'
```

**Health Check:**
```bash
curl http://127.0.0.1:8000/health
```

## API Documentation

Once the server is running, visit:
- **Swagger UI:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

## Roadmap
- [ ] PostgreSQL / MySQL support (replace SQLite)
- [ ] Redis-backed rate limiting
- [ ] JWT token authentication
- [ ] Admin dashboard for managing agents & policies
- [ ] Webhook notifications for blocked attempts
- [ ] Microsoft Presidio integration for advanced PII detection
- [ ] OpenTelemetry tracing
- [ ] Input sanitization / prompt injection detection
