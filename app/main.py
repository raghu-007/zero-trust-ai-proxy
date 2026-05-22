from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timezone
import json

from . import models, database, security, tools
from .middleware import RateLimitMiddleware

# Create the database tables
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(
    title="Zero-Trust AI Agent Proxy",
    description="A secure proxy layer for AI Agents enforcing RBAC, audit logging, and PII redaction.",
    version="1.0.0",
)

# --- Middleware ---

# Rate limiting: 60 requests per minute per IP
app.add_middleware(RateLimitMiddleware, max_requests=60, window_seconds=60)

# CORS: Lock down in production, allow all for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict to specific frontend origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ExecuteRequest(BaseModel):
    tool_name: str
    args: dict


@app.post("/execute")
def execute_tool(
    request: ExecuteRequest,
    agent: models.Agent = Depends(security.get_current_agent),
    db: Session = Depends(database.get_db)
):
    """
    Main endpoint for AI Agents to execute tools via the proxy.
    Enforces RBAC, executes the tool, logs the audit trail, and redacts PII.
    """
    # 1. Check Policy (RBAC)
    is_authorized = security.check_agent_policy(agent, request.tool_name, db)
    
    # 2. Execution & Audit Logging Preparation
    audit_log = models.AuditLog(
        agent_id=agent.id,
        tool_requested=request.tool_name,
        arguments=json.dumps(request.args),
        is_authorized=is_authorized
    )
    
    if not is_authorized:
        db.add(audit_log)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Agent '{agent.name}' is not authorized to use tool '{request.tool_name}'"
        )
        
    # 3. Execute Tool
    try:
        raw_result = tools.execute_tool(request.tool_name, request.args)
    except ValueError as e:
        audit_log.execution_result = str(e)
        db.add(audit_log)
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        audit_log.execution_result = f"Error: {str(e)}"
        db.add(audit_log)
        db.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Tool execution failed")
        
    # 4. Redact PII from the result
    safe_result = security.redact_pii(raw_result)
    
    # 5. Finalize Audit Log
    audit_log.execution_result = safe_result
    db.add(audit_log)
    db.commit()
    
    return json.loads(safe_result)


@app.get("/health")
def health_check():
    """Health check endpoint for monitoring and load balancers."""
    return {
        "status": "ok",
        "version": app.version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
