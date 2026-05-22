from sqlalchemy.orm import Session
import re
import hashlib
from fastapi import HTTPException, status, Depends
from fastapi.security import APIKeyHeader
from . import models, database

API_KEY_NAME = "X-Agent-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def hash_api_key(api_key: str) -> str:
    """
    Hash an API key using SHA-256 for secure storage and comparison.
    In production, consider using bcrypt or argon2 for even stronger hashing.
    """
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def get_agent_by_api_key(api_key: str, db: Session) -> models.Agent:
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key",
        )

    # Hash the incoming key to compare against the stored hash
    hashed_key = hash_api_key(api_key)
    agent = db.query(models.Agent).filter(models.Agent.api_key == hashed_key).first()

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
    Regex-based PII redactor. Scrubs the following patterns before data
    is returned to external LLM providers:

    - Email addresses      → [REDACTED_EMAIL]
    - SSNs (###-##-####)   → [REDACTED_SSN]
    - US Phone numbers     → [REDACTED_PHONE]
    - Credit card numbers  → [REDACTED_CC]
    - IPv4 addresses       → [REDACTED_IP]

    NOTE: In a real enterprise deployment, replace this with Microsoft Presidio
    or a specialized NLP model for more robust detection.
    """
    # Redact Emails
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    redacted = re.sub(email_pattern, "[REDACTED_EMAIL]", text)
    
    # Redact SSNs (###-##-####)
    ssn_pattern = r'\b\d{3}-\d{2}-\d{4}\b'
    redacted = re.sub(ssn_pattern, "[REDACTED_SSN]", redacted)
    
    # Redact US Phone Numbers (various formats)
    # Matches: (123) 456-7890, 123-456-7890, +1-123-456-7890, +11234567890
    phone_pattern = r'(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'
    redacted = re.sub(phone_pattern, "[REDACTED_PHONE]", redacted)
    
    # Redact Credit Card Numbers (with or without separators)
    # Matches: 4111-1111-1111-1111, 4111 1111 1111 1111, 4111111111111111
    cc_pattern = r'\b(?:\d{4}[-\s]?){3}\d{4}\b'
    redacted = re.sub(cc_pattern, "[REDACTED_CC]", redacted)
    
    # Redact IPv4 Addresses (prevent leaking internal network info)
    ipv4_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
    redacted = re.sub(ipv4_pattern, "[REDACTED_IP]", redacted)
    
    return redacted
