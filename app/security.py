from sqlalchemy.orm import Session
import re
from fastapi import HTTPException, status, Depends
from fastapi.security import APIKeyHeader
from . import models, database

API_KEY_NAME = "X-Agent-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def get_agent_by_api_key(api_key: str, db: Session) -> models.Agent:
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key",
        )
    agent = db.query(models.Agent).filter(models.Agent.api_key == api_key).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )
    if not agent.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent is deactivated",
        )
    return agent

async def get_current_agent(
    api_key: str = Depends(api_key_header),
    db: Session = Depends(database.get_db)
):
    return get_agent_by_api_key(api_key, db)

def check_agent_policy(agent: models.Agent, tool_name: str, db: Session) -> bool:
    """Checks if the agent has explicitly been granted access to the tool."""
    policy = db.query(models.Policy).filter(
        models.Policy.agent_id == agent.id,
        models.Policy.tool_name == tool_name
    ).first()
    
    if policy and policy.is_allowed:
        return True
    return False

def redact_pii(text: str) -> str:
    """
    A simple regex-based PII redactor for the MVP.
    In a real enterprise, this would use Microsoft Presidio or a specialized NLP model.
    """
    # Redact Emails
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    redacted = re.sub(email_pattern, "[REDACTED_EMAIL]", text)
    
    # Redact SSNs (###-##-####)
    ssn_pattern = r'\b\d{3}-\d{2}-\d{4}\b'
    redacted = re.sub(ssn_pattern, "[REDACTED_SSN]", redacted)
    
    return redacted
