import asyncio
import hashlib
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, aclosing
from datetime import UTC, datetime
from uuid import uuid4

from langchain_core.messages import HumanMessage
from langgraph.types import Command
from opentelemetry import trace
from opentelemetry.trace import StatusCode
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentlens.checkpoints import checkpoints
from agentlens.config import ROOT, Settings
from agentlens.conversations import ConversationError, create_thread, read_thread
from agentlens.db import Run, RunStep, create_session
from agentlens.graph import ModelCallLimit, build_graph
from agentlens.observability import run_span_context, tracer
from agentlens.replay import RecordedTools, ReplayMismatch
from agentlens.schemas import ExperienceContext, ResumeRequest, RunListQuery
from agentlens.security import audit, identity


class InvestigationFailed(RuntimeError):
    def __init__(self, run_id: str, reason: str):
        self.run_id = run_id
        super().__init__(reason)


async def investigation_events(
    settings: Settings,
    project_id: str,
    prompt: str,
    *,
    thread_id: str | None = None,
    experience: ExperienceContext | None = None,
    resume: ResumeRequest | None = None,
    recording: dict | None = None,
    scenario: dict | None = None,
    model_override: str | None = None,
) -> AsyncIterator[dict]:
    upstream = (
        settings.configured_upstream_model if model_override in {None, settings.model} else None
    )
    if model_override:
        settings = settings.model_copy(update={"model": model_override})
    replay = RecordedTools(recording["payload"]) if recording else None
    with create_session(settings) as session:
        if thread_id is None:
            thread_id = create_thread(session, project_id)["thread_id"]
        else:
            # Authorize the conversation before reading any checkpoint data.
            read_thread(session, thread_id, project_id)
            previous = session.scalar(
                select(Run)
                .where(Run.thread_id == thread_id)
                .order_by(Run.started_at.desc())
                .limit(1)
            )
            if previous is not None and previous.execution_mode != "live":
                raise ConversationError(
                    409,
                    "Isolated execution threads cannot be resumed or "
                    "continued as live sessions; start a new operation",
                )
        async with checkpoints(settings, thread_id) as saver, AsyncExitStack() as stack:
            run = Run(
                id=str(uuid4()),
                thread_id=thread_id,
                project_id=project_id,
                execution_mode="recorded_replay"
                if recording
                else "frozen_scenario"
                if scenario
                else "live",
                recording_id=recording["recording_id"] if recording else None,
                scenario_id=scenario["scenario_id"] if scenario else None,
                source_run_id=recording["source_run_id"]
                if recording
                else scenario["source_run_id"]
                if scenario
                else None,
                status="running",
                input=prompt if resume is None else resume.model_dump_json(),
                output=None,
                versions={
                    "prompt_sha256": hashlib.sha256(
                        (ROOT / "prompts/diagnose.md").read_bytes()
                    ).hexdigest(),
                    "dataset_sha256": hashlib.sha256(
                        (ROOT / "datasets/telemetry.json").read_bytes()
                    ).hexdigest(),
                    "requested_model": settings.model,
                    "configured_upstream_model": upstream,
                    "tool_transport": "recorded/no-mcp" if recording else "mcp/streamable-http",
                    "checkpointer": "AsyncPostgresSaver",
                    "graph_version": "week8-v1",
                    "actor": identity.get().actor if identity.get() else "local-cli",
                    "recording_sha256": recording["sha256"] if recording else None,
                    "scenario_manifest": scenario["manifest"] if scenario else None,
                },
                usage={"input_tokens": 0, "output_tokens": 0},
                started_at=datetime.now(UTC),
            )
            graph = build_graph(settings, session, run, saver, stack, replay=replay)
            config = {
                "configurable": {"thread_id": thread_id},
                "recursion_limit": settings.max_model_calls * 2 + 5,
            }
            snapshot = await graph.aget_state(config)
            if resume is not None:
                if not snapshot.next or snapshot.config["configurable"].get("checkpoint_id") != (
                    resume.checkpoint_id
                ):
                    raise ConversationError(409, "Checkpoint is stale or has no pending work")
                interrupted = any(task.interrupts for task in snapshot.tasks)
                if interrupted and resume.approved is None:
                    raise ConversationError(422, "An interrupted confirmation requires approved")
                if not interrupted and resume.approved is not None:
                    raise ConversationError(409, "This checkpoint is not awaiting confirmation")
                run.source_run_id = snapshot.values["origin_run_id"]
                run.checkpoint_id = resume.checkpoint_id
                graph_input = Command(resume=resume.approved) if interrupted else None
            else:
                if snapshot.next:
                    raise ConversationError(
                        409, "Resume pending work before adding another message"
                    )
                graph_input = {
                    "messages": [HumanMessage(content=prompt)],
                    "model_calls": 0,
                    "diagnosis": None,
                    "origin_run_id": run.id,
                    "evidence_ids": snapshot.values.get("evidence_ids", []),
                    "telemetry_evidence_ids": snapshot.values.get("telemetry_evidence_ids", []),
                    "experience_context": experience.model_dump(mode="json")
                    if experience
                    else None,
                    "experience_approved": None,
                    "experience_id": None,
                }
            parent = trace.get_current_span().get_span_context()
            business_span = tracer.start_span(
                "agentlens.investigate",
                attributes={
                    "agentlens.run_id": run.id,
                    "agentlens.thread_id": thread_id,
                    "agentlens.project_id": project_id,
                },
            )
            span_context = business_span.get_span_context()
            if span_context.is_valid:
                run.trace_id = f"{span_context.trace_id:032x}"
                run.span_id = f"{span_context.span_id:016x}"
                run.request_span_id = f"{parent.span_id:016x}" if parent.is_valid else None
            session.add(run)
            session.commit()
            try:
                audit(
                    settings,
                    action="run.start",
                    resource=run.execution_mode,
                    project=project_id,
                    run_id=run.id,
                )
                yield {
                    "event": "run_started",
                    "run_id": run.id,
                    "thread_id": thread_id,
                    "project_id": project_id,
                    "trace_id": run.trace_id,
                }
                source = graph.astream(
                    graph_input,
                    config,
                    stream_mode=["custom", "updates"],
                    version="v2",
                    durability="sync",
                )
                async with aclosing(source):
                    while True:
                        # SSE prefetch and body iteration run in different contexts. Never
                        # keep an OTel attachment token alive across an async-generator yield.
                        with run_span_context(business_span, run):
                            try:
                                part = await anext(source)
                            except StopAsyncIteration:
                                break
                        if part["type"] == "custom":
                            yield {**part["data"], "run_id": run.id, "thread_id": thread_id}
                snapshot = await graph.aget_state(config)
                run.checkpoint_id = snapshot.config["configurable"]["checkpoint_id"]
                run.output = snapshot.values["diagnosis"]
                interrupts = [i for task in snapshot.tasks for i in task.interrupts]
                if interrupts:
                    run.status = "interrupted"
                    run.interrupt_payload = {"id": interrupts[0].id, "value": interrupts[0].value}
                    terminal = {"event": "run_interrupted", "interrupt": run.interrupt_payload}
                else:
                    run.status = run.output["status"]
                    terminal = {
                        "event": "run_finished",
                        "experience_approved": snapshot.values["experience_approved"],
                        "experience_id": snapshot.values["experience_id"],
                    }
                terminal.update(
                    {
                        "run_id": run.id,
                        "thread_id": thread_id,
                        "status": run.status,
                        "checkpoint_id": run.checkpoint_id,
                        "diagnosis": run.output,
                        "usage": run.usage,
                    }
                )
            except (asyncio.CancelledError, GeneratorExit):
                business_span.set_status(StatusCode.ERROR)
                business_span.set_attribute("error.type", "cancelled")
                run.status = "cancelled"
                run.error = "Invocation cancelled before completion"
                raise
            except Exception as exc:
                business_span.set_status(StatusCode.ERROR)
                business_span.set_attribute("error.type", type(exc).__name__)
                run.status = "replay_mismatch" if isinstance(exc, ReplayMismatch) else "failed"
                if isinstance(exc, ReplayMismatch):
                    run.failure_detail = exc.detail
                elif isinstance(exc, ModelCallLimit):
                    run.failure_detail = {
                        "code": "model_call_limit",
                        "limit": settings.max_model_calls,
                    }
                run.error = f"{type(exc).__name__}: {exc}"
                terminal = {
                    "event": "run_failed",
                    "run_id": run.id,
                    "thread_id": thread_id,
                    "error": run.error,
                    "status": run.status,
                    "failure_detail": run.failure_detail,
                }
            finally:
                run.finished_at = datetime.now(UTC)
                session.commit()
                audit(
                    settings,
                    action="run.finish",
                    resource=run.execution_mode,
                    project=project_id,
                    run_id=run.id,
                    result=run.status,
                    detail={"approved": resume.approved} if resume else {},
                )
                business_span.set_attribute("agentlens.run.status", run.status)
                if run.checkpoint_id:
                    business_span.set_attribute("agentlens.checkpoint_id", run.checkpoint_id)
                business_span.end()
    yield terminal


async def investigate(settings: Settings, project_id: str, prompt: str, **options) -> dict:
    async for event in investigation_events(settings, project_id, prompt, **options):
        if event["event"] == "run_failed":
            raise InvestigationFailed(event["run_id"], event["error"])
        if event["event"] in {"run_finished", "run_interrupted"}:
            return event
    raise RuntimeError("Investigation ended without a terminal event")


def read_run(session: Session, run_id: str, project_id: str | None = None) -> dict | None:
    query = select(Run).where(Run.id == run_id)
    if project_id is not None:
        query = query.where(Run.project_id == project_id)
    run = session.scalar(query)
    if run is None:
        return None
    steps = session.scalars(
        select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.sequence)
    ).all()
    return {
        "run_id": run.id,
        "thread_id": run.thread_id,
        "source_run_id": run.source_run_id,
        "execution_mode": run.execution_mode,
        "recording_id": run.recording_id,
        "scenario_id": run.scenario_id,
        "failure_detail": run.failure_detail,
        "checkpoint_id": run.checkpoint_id,
        "trace_id": run.trace_id,
        "span_id": run.span_id,
        "request_span_id": run.request_span_id,
        "interrupt": run.interrupt_payload,
        "project_id": run.project_id,
        "status": run.status,
        "input": run.input,
        "output": run.output,
        "versions": run.versions,
        "usage": run.usage,
        "error": run.error,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "steps": [
            {
                "sequence": s.sequence,
                "kind": s.kind,
                "name": s.name,
                "input": s.input,
                "output": s.output,
                "error": s.error,
                "duration_ms": s.duration_ms,
                "span_id": s.span_id,
                "source_step_sequence": s.source_step_sequence,
            }
            for s in steps
        ],
    }


def list_runs(session: Session, project_id: str, query: RunListQuery) -> dict:
    conditions = [Run.project_id == project_id]
    if query.thread_id:
        conditions.append(Run.thread_id == query.thread_id)
    if query.status:
        conditions.append(Run.status == query.status)
    rows = session.scalars(
        select(Run)
        .where(*conditions)
        .order_by(Run.started_at.desc(), Run.id.desc())
        .offset(query.offset)
        .limit(query.limit)
    ).all()
    count = session.scalar(select(func.count()).select_from(Run).where(*conditions))
    return {
        "total": count,
        "limit": query.limit,
        "offset": query.offset,
        "runs": [
            {
                "run_id": r.id,
                "thread_id": r.thread_id,
                "project_id": r.project_id,
                "status": r.status,
                "execution_mode": r.execution_mode,
                "source_run_id": r.source_run_id,
                "input": r.input,
                "trace_id": r.trace_id,
                "usage": r.usage,
                "started_at": r.started_at.isoformat(),
                "duration_ms": (r.finished_at - r.started_at).total_seconds() * 1000
                if r.finished_at
                else None,
            }
            for r in rows
        ],
    }
