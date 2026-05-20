# Zero-Trust AI Agent Control Plane

A secure, enterprise-grade proxy layer for AI Agents (like LangChain, AutoGPT, or custom bots).

## The Problem
When deploying AI agents into an enterprise environment, they need access to internal APIs, databases, and infrastructure to be useful. However, giving an LLM direct access to these tools is a massive security risk (Prompt Injection, Data Exfiltration, Accidental Deletion).

## The Solution
This project acts as an **FDE (Forward Deployed Engineering) Control Plane**. The AI agent never executes tools directly. Instead, it sends a request to this proxy.

### Key Features
*   **Role-Based Access Control (RBAC):** Just because an agent wants to run `drop_table`, doesn't mean it can. The proxy checks a database to see if that specific agent is authorized for that specific tool.
*   **Audit Logging:** Every single execution attempt (allowed or blocked) is logged to the database with timestamps, arguments, and the exact result. Ready for SIEM ingestion (Datadog/Splunk).
*   **PII Redaction:** Before returning query results to the agent, the proxy automatically scrubs Personally Identifiable Information (like SSNs and Emails) so they don't leak back to external LLM providers (OpenAI/Anthropic).

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
*This creates an agent named 'DevOps-Bot' with the API Key 'sk-mock-key-123' and gives it permission to run 'github_commit' but NOT 'query_db'.*

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
