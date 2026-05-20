from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    api_key = Column(String, unique=True, index=True)
    is_active = Column(Boolean, default=True)

    policies = relationship("Policy", back_populates="agent")
    audit_logs = relationship("AuditLog", back_populates="agent")

class Policy(Base):
    __tablename__ = "policies"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"))
    tool_name = Column(String, index=True) # e.g., 'github_commit', 'query_db'
    is_allowed = Column(Boolean, default=True)

    agent = relationship("Agent", back_populates="policies")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    agent_id = Column(Integer, ForeignKey("agents.id"))
    tool_requested = Column(String)
    arguments = Column(String) # Store as JSON string
    is_authorized = Column(Boolean)
    execution_result = Column(String, nullable=True) # Store as JSON string or text

    agent = relationship("Agent", back_populates="audit_logs")
