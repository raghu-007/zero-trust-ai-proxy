"""SQLAlchemy storage; legacy raw audit rows are retained but no longer written."""
from datetime import datetime, timezone
from sqlalchemy import create_engine, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool
from .service import AuditUnavailable

Base = declarative_base()


class Store:
    def __init__(self, database_url):
        options = {"connect_args": {"check_same_thread": False, "timeout": 5}}
        if database_url in {"sqlite:///:memory:", "sqlite:///"}:
            options["poolclass"] = StaticPool
        self.engine = create_engine(database_url, **options)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)

    def initialize(self):
        from . import models
        Base.metadata.create_all(self.engine)

    def close(self):
        self.engine.dispose()

    def authenticate(self, digest):
        from .models import Agent
        try:
            with self.sessions() as session:
                return session.scalar(select(Agent.id).where(
                    Agent.api_key == digest, Agent.is_active.is_(True)))
        except SQLAlchemyError:
            raise AuditUnavailable() from None

    def authorize(self, agent_id, tool_name):
        from .models import Policy
        try:
            with self.sessions() as session:
                values = session.scalars(select(Policy.is_allowed).where(
                    Policy.agent_id == agent_id, Policy.tool_name == tool_name)).all()
                return bool(values) and all(value is True for value in values)
        except SQLAlchemyError:
            raise AuditUnavailable() from None

    def begin(self, request_id):
        from .models import AuditEvent
        try:
            with self.sessions.begin() as session:
                session.add(AuditEvent(request_id=request_id, outcome="received"))
        except SQLAlchemyError:
            raise AuditUnavailable() from None

    def _update_event(self, request_id, **values):
        from .models import AuditEvent
        values["updated_at"] = datetime.now(timezone.utc)
        try:
            with self.sessions.begin() as session:
                result = session.execute(update(AuditEvent).where(
                    AuditEvent.request_id == request_id).values(**values))
                if result.rowcount != 1:
                    raise AuditUnavailable()
        except SQLAlchemyError:
            raise AuditUnavailable() from None

    def identify(self, request_id, agent_id, tool_name):
        self._update_event(request_id, agent_id=agent_id, tool_name=tool_name)

    def authorized(self, request_id, agent_id, tool_name):
        self._update_event(request_id, agent_id=agent_id, tool_name=tool_name,
                           outcome="authorized")

    def finish(self, request_id, outcome, status_code):
        self._update_event(request_id, outcome=outcome, status_code=status_code)
