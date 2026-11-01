import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from agentlens.db import KnowledgeDocument, Run, Thread
from agentlens.schemas import ExperienceContext, ExperienceQuery


class ConversationError(ValueError):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        super().__init__(detail)


def create_thread(session: Session, project_id: str) -> dict:
    thread = Thread(id=str(uuid4()), project_id=project_id, created_at=datetime.now(UTC))
    session.add(thread)
    session.commit()
    return {
        "thread_id": thread.id,
        "project_id": project_id,
        "created_at": thread.created_at.isoformat(),
    }


def read_thread(session: Session, thread_id: str, project_id: str) -> dict:
    thread = session.scalar(
        select(Thread).where(Thread.id == thread_id, Thread.project_id == project_id)
    )
    if thread is None:
        raise ConversationError(404, "Thread not found in this project")
    latest = session.scalar(
        select(Run).where(Run.thread_id == thread_id).order_by(Run.started_at.desc()).limit(1)
    )
    return {
        "thread_id": thread.id,
        "project_id": thread.project_id,
        "created_at": thread.created_at.isoformat(),
        "latest_run_id": latest.id if latest else None,
        "status": latest.status if latest else "idle",
        "checkpoint_id": latest.checkpoint_id if latest else None,
        "interrupt": latest.interrupt_payload if latest else None,
    }


def archive_experience(session: Session, project_id: str, state: dict) -> str:
    context = ExperienceContext.model_validate(state["experience_context"])
    source_run = state["origin_run_id"]
    document_id = f"experience-{source_run}"
    content = json.dumps(
        {
            "diagnosis": state["diagnosis"],
            "applicability": context.applicability,
            "service": context.service,
            "start_time": context.start_time.isoformat(),
            "end_time": context.end_time.isoformat(),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    # A crash after this commit but before the graph checkpoint can re-enter this node.
    session.execute(
        insert(KnowledgeDocument)
        .values(
            id=document_id,
            project_id=project_id,
            title=f"{context.service} 已确认故障经验",
            source=f"runs/{source_run}",
            revision=hashlib.sha256(content.encode()).hexdigest(),
            kind="incident_experience",
            origin_run_id=source_run,
            service=context.service,
            start_time=context.start_time,
            end_time=context.end_time,
            applicability=context.applicability,
            content=content,
        )
        .on_conflict_do_nothing(index_elements=[KnowledgeDocument.origin_run_id])
    )
    session.commit()
    return document_id


def search_experiences(session: Session, project_id: str, query: ExperienceQuery) -> dict:
    docs = session.scalars(
        select(KnowledgeDocument)
        .where(
            KnowledgeDocument.project_id == project_id,
            KnowledgeDocument.kind == "incident_experience",
            KnowledgeDocument.service == query.service,
        )
        .order_by(KnowledgeDocument.created_at.desc(), KnowledgeDocument.id)
        .limit(query.limit)
    ).all()
    return {
        "experiences": [
            {
                "evidence_id": doc.id,
                "project_id": doc.project_id,
                "kind": doc.kind,
                "source": doc.source,
                "origin_run_id": doc.origin_run_id,
                "revision": doc.revision,
                "service": doc.service,
                "start_time": doc.start_time.isoformat(),
                "end_time": doc.end_time.isoformat(),
                "applicability": doc.applicability,
                "content": doc.content,
                "confirmed_at": doc.created_at.isoformat(),
            }
            for doc in docs
        ]
    }
