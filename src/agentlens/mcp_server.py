from functools import wraps
from typing import Literal

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from pydantic import AwareDatetime
from sqlalchemy import select

from agentlens.config import Settings
from agentlens.conversations import search_experiences
from agentlens.db import Run, create_session
from agentlens.frozen import tool_session
from agentlens.knowledge import search_runbooks
from agentlens.observability import configure_tracing
from agentlens.sandbox import (
    AnalysisAccessDenied,
    SandboxExecutionError,
    SandboxUnavailable,
    analysis_result,
)
from agentlens.schemas import AnalysisQuery, ExperienceQuery, LogQuery, MetricQuery, RunbookQuery
from agentlens.security import IdentityMiddleware, audit, identity
from agentlens.tools import query_metrics, search_logs

mcp = MCPServer("AgentLens telemetry")


def project_scope(ctx: Context) -> str:
    project_id = ctx.headers.get("x-agentlens-project") if ctx.headers is not None else None
    current = identity.get()
    if current is None or project_id != current.project:
        raise ValueError("Project is not authorized")
    return project_id


def audited(function):
    @wraps(function)
    def call(*args, **kwargs):
        ctx = kwargs["ctx"]
        project = project_scope(ctx)
        run_id = ctx.headers.get("x-agentlens-run")
        if run_id:
            with create_session(Settings()) as session:
                if (
                    session.scalar(
                        select(Run.id).where(Run.id == run_id, Run.project_id == project)
                    )
                    is None
                ):
                    audit(
                        Settings(),
                        action="tool." + function.__name__,
                        resource=run_id,
                        decision="deny",
                        result="run_scope_mismatch",
                        project=project,
                    )
                    raise ToolError("Run is not in the authorized project")
        try:
            result = function(*args, **kwargs)
        except Exception as exc:
            audit(
                Settings(),
                action="tool." + function.__name__,
                resource=function.__name__,
                result=type(exc).__name__,
                decision="deny" if isinstance(exc, AnalysisAccessDenied) else "allow",
                project=project,
                run_id=run_id,
            )
            if isinstance(exc, (SandboxUnavailable, SandboxExecutionError, ValueError)):
                raise ToolError(str(exc)) from exc
            raise
        audit(
            Settings(),
            action="tool." + function.__name__,
            resource=function.__name__,
            project=project,
            run_id=run_id,
        )
        return result

    return call


@mcp.tool(name="search_logs", structured_output=True)
@audited
def logs(
    service: str,
    start_time: AwareDatetime,
    end_time: AwareDatetime,
    ctx: Context,
    level: Literal["INFO", "WARN", "ERROR"] | None = None,
    limit: int = 50,
) -> dict[str, list[dict]]:
    """Query logs in the current project. Times include timezone; interval is [start, end).

    Returns citeable evidence_id values. Limit is 1-200.
    """
    project_id = project_scope(ctx)
    query = LogQuery(
        service=service, start_time=start_time, end_time=end_time, level=level, limit=limit
    )
    with tool_session(Settings(), project_id, ctx.headers.get("x-agentlens-scenario")) as session:
        return search_logs(session, project_id, query)


@mcp.tool(name="query_metrics", structured_output=True)
@audited
def metrics(
    service: str,
    start_time: AwareDatetime,
    end_time: AwareDatetime,
    ctx: Context,
    metric_name: str | None = None,
    limit: int = 100,
) -> dict[str, list[dict]]:
    """Query metrics in the current project and [start_time, end_time).

    Leave metric_name unset to inspect available metrics. Returns citeable evidence. Limit is 1-300.
    """
    project_id = project_scope(ctx)
    query = MetricQuery(
        service=service,
        start_time=start_time,
        end_time=end_time,
        metric_name=metric_name,
        limit=limit,
    )
    with tool_session(Settings(), project_id, ctx.headers.get("x-agentlens-scenario")) as session:
        return query_metrics(session, project_id, query)


@mcp.tool(name="search_runbooks", structured_output=True)
@audited
def runbooks(query: str, ctx: Context, top_k: int = 3) -> dict[str, list[dict]]:
    """Search the current project's troubleshooting handbooks using symptoms and error terms.

    Use observed service/component names and error messages in query. Returns citeable chunk
    evidence_id, source, revision and content. Handbooks guide checks; they are not live telemetry.
    top_k is 1-10. Query is 1-2000 characters. Uses fixed BGE embeddings and pgvector cosine search.
    """
    project_id = project_scope(ctx)
    request = RunbookQuery(query=query, top_k=top_k)
    settings = Settings()
    with tool_session(settings, project_id, ctx.headers.get("x-agentlens-scenario")) as session:
        return search_runbooks(session, settings, project_id, request)


@mcp.tool(name="search_experiences", structured_output=True)
@audited
def experiences(service: str, ctx: Context, limit: int = 5) -> dict[str, list[dict]]:
    """Find human-confirmed incident experience for a service in the current project.

    Use for related past incidents and applicable investigation steps. Results are historical
    knowledge, not live evidence for a new incident. Returns citeable IDs and original run/time.
    Exact service match, latest confirmations first. Limit is 1-20.
    """
    project_id = project_scope(ctx)
    query = ExperienceQuery(service=service, limit=limit)
    with tool_session(Settings(), project_id, ctx.headers.get("x-agentlens-scenario")) as session:
        return search_experiences(session, project_id, query)


@mcp.tool(name="analyze_logs", structured_output=True)
@audited
def analyze_logs(evidence_ids: list[str], python_code: str, ctx: Context) -> dict[str, list[dict]]:
    """Run Python statistics on logs already retrieved in THIS run, using OpenShell only.

    Use only when the user requests statistical analysis. logs is a list of authorized rows.
    Print exactly one JSON value. No network, credentials, package installs or host files.
    Maximum 100 log IDs, code 6000 chars, 8 seconds, 256MiB, output 64KiB.
    Runtime absence is a tool error; never claim analysis succeeded without its result.
    """
    return analysis_result(
        Settings(),
        project_scope(ctx),
        ctx.headers.get("x-agentlens-run"),
        AnalysisQuery(evidence_ids=evidence_ids, python_code=python_code),
    )


configure_tracing("agentlens-mcp")
app = OpenTelemetryMiddleware(
    IdentityMiddleware(mcp.streamable_http_app(stateless_http=True), mcp=True),
    exclude_spans=["send", "receive"],
)
