from datetime import datetime
from functools import lru_cache
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from agentlens.config import Settings


class Base(DeclarativeBase):
    pass


class LogEvent(Base):
    __tablename__ = "log_events"
    __table_args__ = (Index("ix_logs_scope_time", "project_id", "service", "timestamp"),)

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(50))
    service: Mapped[str] = mapped_column(String(80))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    level: Mapped[str] = mapped_column(String(10))
    message: Mapped[str] = mapped_column(Text)


class MetricPoint(Base):
    __tablename__ = "metric_points"
    __table_args__ = (Index("ix_metrics_scope_time", "project_id", "service", "timestamp"),)

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(50))
    service: Mapped[str] = mapped_column(String(80))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    name: Mapped[str] = mapped_column(String(80))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(30))


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_scope_time", "project_id", "timestamp"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(String(50))
    actor: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(120))
    resource: Mapped[str] = mapped_column(String(240))
    run_id: Mapped[str | None] = mapped_column(String(36))
    decision: Mapped[str] = mapped_column(String(20))
    result: Mapped[str] = mapped_column(String(60))
    detail: Mapped[dict] = mapped_column(JSON)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (Index("ix_runs_thread_started", "thread_id", "started_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    thread_id: Mapped[str | None] = mapped_column(ForeignKey("threads.id"))
    source_run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"))
    execution_mode: Mapped[str] = mapped_column(String(20), default="live", server_default="live")
    recording_id: Mapped[str | None] = mapped_column(ForeignKey("recordings.id"))
    scenario_id: Mapped[str | None] = mapped_column(ForeignKey("frozen_scenarios.id"))
    failure_detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    checkpoint_id: Mapped[str | None] = mapped_column(String(100))
    trace_id: Mapped[str | None] = mapped_column(String(32), index=True)
    span_id: Mapped[str | None] = mapped_column(String(16))
    request_span_id: Mapped[str | None] = mapped_column(String(16))
    interrupt_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    project_id: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30))
    input: Mapped[str] = mapped_column(Text)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    versions: Mapped[dict[str, Any]] = mapped_column(JSON)
    usage: Mapped[dict[str, int]] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(Text)
    revision: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(40), default="runbook")
    origin_run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"), unique=True)
    service: Mapped[str | None] = mapped_column(String(80))
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applicability: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id"))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(512))
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON)


class RunStep(Base):
    __tablename__ = "run_steps"
    __table_args__ = (Index("ix_steps_run_sequence", "run_id", "sequence", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    sequence: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    input: Mapped[dict[str, Any]] = mapped_column(JSON)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[float] = mapped_column(Float)
    span_id: Mapped[str | None] = mapped_column(String(16))
    source_step_sequence: Mapped[int | None] = mapped_column(Integer)


class Recording(Base):
    __tablename__ = "recordings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(50), index=True)
    source_run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FrozenScenario(Base):
    __tablename__ = "frozen_scenarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(50), index=True)
    source_run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"))
    schema_name: Mapped[str] = mapped_column(String(63), unique=True)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TraceSpan(Base):
    __tablename__ = "trace_spans"

    trace_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    span_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    parent_span_id: Mapped[str | None] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(30))
    start_ns: Mapped[int] = mapped_column(BigInteger)
    end_ns: Mapped[int] = mapped_column(BigInteger)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON)
    resource: Mapped[dict[str, Any]] = mapped_column(JSON)
    scope: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    events: Mapped[list[dict[str, Any]]] = mapped_column(JSON)


@lru_cache
def database_engine(database_url: str):
    return create_engine(database_url)


def create_session(settings: Settings) -> Session:
    return Session(
        database_engine(settings.database_url.get_secret_value()), expire_on_commit=False
    )
