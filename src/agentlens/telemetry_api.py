"""Internal-only OTLP ingest; never mounted on the user-facing API."""

from hmac import compare_digest
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Request, Response
from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)

from agentlens.config import Settings
from agentlens.db import create_session
from agentlens.telemetry import ingest_traces

app = FastAPI(title="AgentLens internal OTLP")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/traces")
async def traces(request: Request, x_agentlens_ingest_key: Annotated[str, Header()]):
    settings = Settings()
    if not compare_digest(x_agentlens_ingest_key, settings.otlp_ingest_key.get_secret_value()):
        raise HTTPException(403, "Collector ingest key required")
    if request.headers.get("content-type", "").split(";")[0] != "application/x-protobuf":
        raise HTTPException(415, "Only OTLP/HTTP protobuf traces are supported")
    body = await request.body()
    if len(body) > 8 * 1024 * 1024:
        raise HTTPException(413, "OTLP batch exceeds 8 MiB")
    try:
        batch = ExportTraceServiceRequest.FromString(body)
        with create_session(settings) as session:
            ingest_traces(session, batch)
    except (DecodeError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return Response(
        ExportTraceServiceResponse().SerializeToString(), media_type="application/x-protobuf"
    )
