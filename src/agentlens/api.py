import json
from contextlib import aclosing
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from sqlalchemy import select

from agentlens.agent import (
    InvestigationFailed,
    investigate,
    investigation_events,
    list_runs,
    read_run,
)
from agentlens.checkpoints import checkpoints
from agentlens.config import ROOT, Settings
from agentlens.conversations import (
    ConversationError,
    create_thread,
    read_thread,
    search_experiences,
)
from agentlens.db import AuditEvent, create_session
from agentlens.evaluation_api import (
    list_evaluations,
    report_path,
    scoped_comparison,
    scoped_report,
)
from agentlens.executions import execute_recording, execute_scenario, execution_difference
from agentlens.frozen import freeze_scenario, list_scenarios, read_scenario
from agentlens.observability import configure_tracing
from agentlens.operations import operation_summary, prometheus_export
from agentlens.recordings import capture_recording, list_recordings, read_recording
from agentlens.schemas import (
    ExperienceQuery,
    FreezeRequest,
    InvokeRequest,
    ReplayRequest,
    ResumeRequest,
    RunListQuery,
    ThreadRunRequest,
)
from agentlens.security import IdentityMiddleware, identity
from agentlens.telemetry import read_trace

app = FastAPI(title="AgentLens", version="0.1.0")
app.add_middleware(IdentityMiddleware)
ProjectScope = Annotated[str, Header(alias="X-AgentLens-Project", min_length=1, max_length=50)]


@app.exception_handler(ConversationError)
async def conversation_error(request, exc: ConversationError):
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


@app.exception_handler(InvestigationFailed)
async def investigation_failed(request, exc: InvestigationFailed):
    return JSONResponse(status_code=502, content={"run_id": exc.run_id, "error": str(exc)})


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/identity")
def current_identity():
    current = identity.get()
    return {"actor": current.actor, "project": current.project}


@app.get("/audit-events")
def audit_events(project: ProjectScope, limit: Annotated[int, Query(ge=1, le=200)] = 50):
    with create_session(Settings()) as session:
        rows = session.scalars(
            select(AuditEvent)
            .where(AuditEvent.project_id == project)
            .order_by(AuditEvent.timestamp.desc())
            .limit(limit)
        )
        return {
            "events": [
                {
                    "id": r.id,
                    "actor": r.actor,
                    "action": r.action,
                    "resource": r.resource,
                    "run_id": r.run_id,
                    "decision": r.decision,
                    "result": r.result,
                    "detail": r.detail,
                    "timestamp": r.timestamp.isoformat(),
                }
                for r in rows
            ]
        }


@app.get("/operations")
def operations(project: ProjectScope):
    with create_session(Settings()) as session:
        return operation_summary(session, project)


@app.get("/metrics", response_class=Response)
def metrics_export(project: ProjectScope):
    with create_session(Settings()) as session:
        return Response(
            prometheus_export(session, project),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )


@app.post("/agent/invoke")
async def invoke(request: InvokeRequest):
    if request.project_id != identity.get().project:
        raise HTTPException(403, "Project is not authorized")
    return await investigate(Settings(), request.project_id, request.prompt)


@app.post("/agent/stream")
async def stream(request: InvokeRequest):
    if request.project_id != identity.get().project:
        raise HTTPException(403, "Project is not authorized")
    return await stream_response(
        investigation_events(Settings(), request.project_id, request.prompt)
    )


async def stream_response(source):
    # Resolve scope/conflict errors before sending HTTP 200 and opening the SSE body.
    first = await anext(source)

    async def events():
        async with aclosing(source):
            yield f"event: {first['event']}\ndata: {json.dumps(first, ensure_ascii=False)}\n\n"
            async for event in source:
                yield f"event: {event['event']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/runs/{run_id}")
def get_run(run_id: str, project: ProjectScope):
    with create_session(Settings()) as session:
        result = read_run(session, run_id, project)
    if result is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return result


@app.get("/runs")
def runs(project: ProjectScope, query: Annotated[RunListQuery, Query()]):
    with create_session(Settings()) as session:
        return list_runs(session, project, query)


@app.get("/traces/{trace_id}")
def get_trace(trace_id: str, run_id: str, project: ProjectScope):
    with create_session(Settings()) as session:
        return read_trace(session, trace_id, run_id, project)


@app.post("/threads", status_code=201)
def new_thread(project: ProjectScope):
    with create_session(Settings()) as session:
        return create_thread(session, project)


@app.get("/threads/{thread_id}")
async def get_thread(thread_id: str, project: ProjectScope):
    settings = Settings()
    with create_session(settings) as session:
        result = read_thread(session, thread_id, project)
    async with checkpoints(settings) as saver:
        checkpoint = await saver.aget_tuple({"configurable": {"thread_id": thread_id}})
        if checkpoint:
            result["checkpoint_id"] = checkpoint.config["configurable"]["checkpoint_id"]
    return result


@app.post("/threads/{thread_id}/runs")
async def thread_run(
    thread_id: str, request: ThreadRunRequest, project: ProjectScope, stream: bool = False
):
    options = {"thread_id": thread_id, "experience": request.experience}
    if stream:
        return await stream_response(
            investigation_events(Settings(), project, request.prompt, **options)
        )
    return await investigate(Settings(), project, request.prompt, **options)


@app.post("/threads/{thread_id}/resume")
async def resume_thread(
    thread_id: str, request: ResumeRequest, project: ProjectScope, stream: bool = False
):
    options = {"thread_id": thread_id, "resume": request}
    if stream:
        return await stream_response(investigation_events(Settings(), project, "", **options))
    return await investigate(Settings(), project, "", **options)


@app.get("/experiences")
def experiences(project: ProjectScope, query: Annotated[ExperienceQuery, Query()]):
    with create_session(Settings()) as session:
        return search_experiences(session, project, query)


@app.get("/evaluations")
def evaluations(project: ProjectScope):
    return {"evaluations": list_evaluations(ROOT / "reports/experiments", project)}


@app.get("/evaluations/{evaluation_id}")
def evaluation_detail(evaluation_id: str, project: ProjectScope):
    return scoped_report(report_path(ROOT / "reports/experiments", evaluation_id), project)


@app.get("/evaluation-comparison")
def evaluation_comparison(baseline: str, candidate: str, project: ProjectScope):
    return scoped_comparison(ROOT / "reports/experiments", baseline, candidate, project)


@app.post("/runs/{run_id}/recordings", status_code=201)
async def record_run(run_id: str, project: ProjectScope):
    return await capture_recording(Settings(), run_id, project)


@app.get("/recordings")
def recordings(project: ProjectScope):
    with create_session(Settings()) as session:
        return {"recordings": list_recordings(session, project)}


@app.get("/recordings/{recording_id}")
def recording_detail(recording_id: str, project: ProjectScope):
    with create_session(Settings()) as session:
        return read_recording(session, recording_id, project)


def execution_response(result: dict):
    if result["event"] == "run_failed":
        return JSONResponse(
            status_code=409 if result["status"] == "replay_mismatch" else 502, content=result
        )
    return result


@app.post("/recordings/{recording_id}/replay")
async def replay_recording(recording_id: str, request: ReplayRequest, project: ProjectScope):
    return execution_response(
        await execute_recording(Settings(), recording_id, project, request.model)
    )


@app.post("/scenarios", status_code=201)
def freeze(request: FreezeRequest, project: ProjectScope):
    return freeze_scenario(Settings(), request.case_id, project, request.source_run_id)


@app.get("/scenarios")
def scenarios(project: ProjectScope):
    with create_session(Settings()) as session:
        return {"scenarios": list_scenarios(session, project)}


@app.get("/scenarios/{scenario_id}")
def scenario_detail(scenario_id: str, project: ProjectScope):
    with create_session(Settings()) as session:
        return read_scenario(session, scenario_id, project)


@app.post("/scenarios/{scenario_id}/evaluate")
async def evaluate_scenario(scenario_id: str, request: ReplayRequest, project: ProjectScope):
    return execution_response(
        await execute_scenario(Settings(), scenario_id, project, request.model)
    )


@app.get("/run-comparison")
def run_comparison(baseline: str, candidate: str, project: ProjectScope):
    return execution_difference(Settings(), baseline, candidate, project)


if (ROOT / "web/dist").is_dir():
    app.mount("/workbench", StaticFiles(directory=ROOT / "web/dist", html=True), name="workbench")

configure_tracing("agentlens-api")
FastAPIInstrumentor.instrument_app(
    app,
    exclude_spans=["send", "receive"],
    excluded_urls=(
        r"/health(?:$|\?)|^https?://[^/]+/"
        r"(?:runs|traces|workbench|experiences)(?:$|[/?])"
    ),
)
