"""The chosen OTLP/HTTP protobuf subset, conversion, deduplication and scoped reads."""

from datetime import UTC, datetime

from opentelemetry.proto.trace.v1.trace_pb2 import Span, Status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from agentlens.conversations import ConversationError
from agentlens.db import Run, RunStep, TraceSpan

# Headers, URLs, message content, exception messages and stack traces are not stored.
SAFE_ATTRIBUTES = {
    "agentlens.run_id",
    "agentlens.thread_id",
    "agentlens.project_id",
    "agentlens.step.sequence",
    "agentlens.step.kind",
    "agentlens.tool.name",
    "agentlens.evidence.count",
    "agentlens.retrieval.strategy",
    "agentlens.checkpoint_id",
    "agentlens.run.status",
    "agentlens.tool.error",
    "agentlens.requested_model",
    "gen_ai.operation.name",
    "gen_ai.system",
    "gen_ai.provider.name",
    "gen_ai.request.model",
    "gen_ai.response.model",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "http.method",
    "http.route",
    "http.status_code",
    "http.request.method",
    "http.response.status_code",
    "server.address",
    "server.port",
    "network.protocol.version",
    "rpc.system",
    "rpc.method",
    "error.type",
    "exception.type",
}
SAFE_RESOURCE = {"service.name", "service.version", "telemetry.sdk.name", "telemetry.sdk.version"}


def any_value(value):
    kind = value.WhichOneof("value")
    if kind == "array_value":
        return [any_value(v) for v in value.array_value.values]
    if kind == "kvlist_value":
        return {item.key: any_value(item.value) for item in value.kvlist_value.values}
    if kind == "bytes_value":
        return value.bytes_value.hex()
    return getattr(value, kind) if kind else None


def ingest_traces(session, request):
    rows = []
    for resource in request.resource_spans:
        resource_attrs = {
            a.key: any_value(a.value)
            for a in resource.resource.attributes
            if a.key in SAFE_RESOURCE
        }
        for scope in resource.scope_spans:
            for span in scope.spans:
                if len(span.trace_id) != 16 or not any(span.trace_id):
                    raise ValueError("OTLP trace_id must contain 16 nonzero bytes")
                if len(span.span_id) != 8 or not any(span.span_id):
                    raise ValueError("OTLP span_id must contain 8 nonzero bytes")
                if span.parent_span_id and len(span.parent_span_id) != 8:
                    raise ValueError("OTLP parent_span_id must contain 8 bytes")
                if span.start_time_unix_nano <= 0 or span.end_time_unix_nano < (
                    span.start_time_unix_nano
                ):
                    raise ValueError("OTLP span times must be positive and ordered")
                rows.append(
                    {
                        "trace_id": span.trace_id.hex(),
                        "span_id": span.span_id.hex(),
                        "parent_span_id": span.parent_span_id.hex()
                        if span.parent_span_id
                        else None,
                        "name": span.name,
                        "kind": Span.SpanKind.Name(span.kind),
                        "start_ns": span.start_time_unix_nano,
                        "end_ns": span.end_time_unix_nano,
                        "attributes": {
                            a.key: any_value(a.value)
                            for a in span.attributes
                            if a.key in SAFE_ATTRIBUTES
                        },
                        "resource": resource_attrs,
                        "scope": scope.scope.name,
                        "status": Status.StatusCode.Name(span.status.code),
                        "events": [
                            {
                                "name": event.name,
                                "time_ns": str(event.time_unix_nano),
                                "attributes": {
                                    a.key: any_value(a.value)
                                    for a in event.attributes
                                    if a.key in SAFE_ATTRIBUTES
                                },
                            }
                            for event in span.events
                        ],
                    }
                )
    if rows:
        session.execute(
            insert(TraceSpan).on_conflict_do_nothing(
                index_elements=[TraceSpan.trace_id, TraceSpan.span_id]
            ),
            rows,
        )
    session.commit()


def read_trace(session, trace_id: str, run_id: str, project_id: str) -> dict:
    run = session.scalar(
        select(Run).where(Run.id == run_id, Run.project_id == project_id, Run.trace_id == trace_id)
    )
    if run is None:
        raise ConversationError(404, "Trace not found for this run in this project")
    spans = session.scalars(
        select(TraceSpan)
        .where(TraceSpan.trace_id == trace_id)
        .order_by(TraceSpan.start_ns, TraceSpan.span_id)
    ).all()
    # A caller can reuse an incoming traceparent across projects. Expose only this run's
    # locally recorded request subtree, not every span sharing the same trace_id.
    root = run.request_span_id or run.span_id
    allowed = {root, run.span_id} | set(
        session.scalars(
            select(RunStep.span_id).where(RunStep.run_id == run_id, RunStep.span_id.is_not(None))
        )
    )
    changed = True
    while changed:
        before = len(allowed)
        allowed.update(s.span_id for s in spans if s.parent_span_id in allowed)
        changed = len(allowed) != before
    visible = [s for s in spans if s.span_id in allowed]
    return {
        "trace_id": trace_id,
        "run_id": run_id,
        "root_span_id": root,
        "business_span_id": run.span_id,
        "business_status": run.status,
        "business_finished": run.finished_at is not None,
        "request_span_received": any(s.span_id == root for s in visible),
        "spans": [
            {
                "span_id": s.span_id,
                "parent_span_id": s.parent_span_id,
                "name": s.name,
                "kind": s.kind,
                "start_ns": str(s.start_ns),
                "end_ns": str(s.end_ns),
                "duration_ms": (s.end_ns - s.start_ns) / 1_000_000,
                "started_at": datetime.fromtimestamp(s.start_ns / 1e9, UTC).isoformat(),
                "attributes": s.attributes,
                "resource": s.resource,
                "scope": s.scope,
                "status": s.status,
                "events": s.events,
            }
            for s in visible
        ],
    }
