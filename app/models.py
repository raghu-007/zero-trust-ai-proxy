from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from .database import Base


class Agent(Base):
    __tablename__ = "agents"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    api_key = Column(String, unique=True, index=True)
    is_active = Column(Boolean, default=True)


class Policy(Base):
    __tablename__ = "policies"
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"))
    tool_name = Column(String, index=True)
    is_allowed = Column(Boolean, default=True)


class AuditLog(Base):
    """Legacy schema only. Existing sensitive rows are not automatically erased."""
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True))
    agent_id = Column(Integer, ForeignKey("agents.id"))
    tool_requested = Column(String)
    arguments = Column(String)
    is_authorized = Column(Boolean)
    execution_result = Column(String, nullable=True)


class AuditEvent(Base):
    """Metadata only: never arguments, results, keys, IPs, or exception messages."""
    __tablename__ = "audit_events_v2"
    request_id = Column(String(32), primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc))
    agent_id = Column(Integer, nullable=True)
    tool_name = Column(String(64), nullable=True)
    outcome = Column(String(32), nullable=False)
    status_code = Column(Integer, nullable=True)
