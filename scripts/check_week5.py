"""OTel/Collector/PG contract checks. Model decisions and export timing are controlled."""

import asyncio
import json
import time
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import httpx
from check_week4 import ScriptedProvider
from opentelemetry.exporter.otlp.proto.common._internal.trace_encoder import encode_spans
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import func, select

from agentlens.agent import investigate, read_run
from agentlens.config import ROOT, Settings
from agentlens.db import Run, TraceSpan, create_session
from agentlens.observability import configure_tracing


def wait_for(client, path, predicate):
    for _ in range(80):
        response = client.get(path)
        response.raise_for_status()
        value = response.json()
        if predicate(value):
            return value
        time.sleep(0.1)
    raise AssertionError("Expected OTLP fragment did not arrive within 8 seconds")


def main():
    settings = Settings()
    exporter = InMemorySpanExporter()
    with patch("agentlens.observability.OTLPSpanExporter", return_value=exporter):
        provider = configure_tracing("agentlens-contracts")
    with patch("agentlens.graph.ChatOpenAI", return_value=ScriptedProvider()):
        result = asyncio.run(
            investigate(settings, "project-a", "Controlled delayed OTel probe"),
            loop_factory=asyncio.SelectorEventLoop,
        )
    provider.force_flush()
    with create_session(settings) as session:
        run = read_run(session, result["run_id"])
    captured = [
        s for s in exporter.get_finished_spans() if f"{s.context.trace_id:032x}" == run["trace_id"]
    ]
    checks = {"business_completed_with_export_held": run["status"] == "diagnosed"}
    assert captured and run["span_id"]
    all_batch = encode_spans(captured)
    child_batch = encode_spans(
        [s for s in captured if f"{s.context.span_id:016x}" != run["span_id"]]
    )
    root_batch = encode_spans(
        [s for s in captured if f"{s.context.span_id:016x}" == run["span_id"]]
    )
    root = root_batch.resource_spans[0].scope_spans[0].spans[0]
    canary = "not-a-real-key-telemetry-canary"
    for key in ["http.request.header.authorization", "api_key", "gen_ai.input.messages"]:
        root.attributes.add(key=key).value.string_value = canary
    root.events.add(name="exception").attributes.add(
        key="exception.message"
    ).value.string_value = canary
    root_batch.resource_spans[0].resource.attributes.add(key="secret").value.string_value = canary
    path = f"/traces/{run['trace_id']}?run_id={run['run_id']}"
    collector = "http://127.0.0.1:4318/v1/traces"
    headers = {"content-type": "application/x-protobuf"}
    with httpx.Client(
        base_url="http://127.0.0.1:8000",
        trust_env=False,
        timeout=10,
        headers={"X-AgentLens-Project": "project-a"},
    ) as client:
        before = client.get(path).json()
        checks["root_absent_before_export"] = not before["request_span_received"]
        response = client.post(collector, content=child_batch.SerializeToString(), headers=headers)
        response.raise_for_status()
        partial = wait_for(client, path, lambda value: bool(value["spans"]))
        checks["partial_children_visible_without_root"] = not partial["request_span_received"]
        client.post(
            collector, content=root_batch.SerializeToString(), headers=headers
        ).raise_for_status()
        complete = wait_for(client, path, lambda value: value["request_span_received"])
        checks["late_root_appends_to_existing_trace"] = len(complete["spans"]) > len(
            partial["spans"]
        )
        checks["metadata_policy_excludes_sensitive_content"] = canary not in json.dumps(complete)
        checks["mcp_server_joins_trace"] = any(
            s["resource"].get("service.name") == "agentlens-mcp" for s in complete["spans"]
        )
        sdk_ids = [f"{s.context.span_id:016x}" for s in captured]
        client.post(
            collector, content=all_batch.SerializeToString(), headers=headers
        ).raise_for_status()
        wait_for(
            client,
            path,
            lambda value: (
                len({s["span_id"] for s in value["spans"]} & set(sdk_ids)) == len(sdk_ids)
            ),
        )
        with create_session(settings) as session:
            count = session.scalar(
                select(func.count())
                .select_from(TraceSpan)
                .where(TraceSpan.trace_id == run["trace_id"], TraceSpan.span_id.in_(sdk_ids))
            )
        checks["duplicate_delivery_deduplicates"] = count == len(set(sdk_ids))
        # Deliberately reuse a trace_id in another project. The run's trusted root, not
        # producer-supplied attributes, is the authorization anchor.
        other_id, other_span = str(uuid4()), "f123456789abcdef"
        with create_session(settings) as session:
            session.add(
                Run(
                    id=other_id,
                    project_id="project-b",
                    trace_id=run["trace_id"],
                    span_id=other_span,
                    status="insufficient_evidence",
                    input="Shared trace scope contract probe",
                    output=None,
                    versions={},
                    usage={"input_tokens": 0, "output_tokens": 0},
                    started_at=datetime.now(UTC),
                    finished_at=datetime.now(UTC),
                )
            )
            session.commit()
        shared = ExportTraceServiceRequest()
        (
            shared.resource_spans.add()
            .scope_spans.add()
            .spans.add(
                trace_id=bytes.fromhex(run["trace_id"]),
                span_id=bytes.fromhex(other_span),
                name="other-project-private-operation",
                start_time_unix_nano=time.time_ns(),
                end_time_unix_nano=time.time_ns(),
            )
        )
        internal_headers = {
            **headers,
            "X-AgentLens-Ingest-Key": settings.otlp_ingest_key.get_secret_value(),
        }
        internal = "http://127.0.0.1:8001/v1/traces"
        client.post(
            internal, content=shared.SerializeToString(), headers=internal_headers
        ).raise_for_status()
        own = client.get(path).json()
        checks["shared_trace_id_does_not_leak_other_project"] = all(
            row["span_id"] != other_span for row in own["spans"]
        )
        other_headers = {"X-AgentLens-Project": "project-b"}
        checks["cross_project_trace_read_404"] = (
            client.get(path, headers=other_headers).status_code == 404
        )
        own_other = client.get(
            f"/traces/{run['trace_id']}?run_id={other_id}", headers=other_headers
        ).json()
        checks["other_project_only_sees_own_subtree"] = [
            r["span_id"] for r in own_other["spans"]
        ] == [other_span]
        checks["run_list_filters_thread"] = all(
            row["thread_id"] == run["thread_id"]
            for row in client.get(f"/runs?thread_id={run['thread_id']}").json()["runs"]
        )
        checks["invalid_list_limit_422"] = client.get("/runs?limit=0").status_code == 422
        checks["ingest_separate_from_public_api"] = client.post("/v1/traces").status_code == 404
        checks["ingest_key_required"] = (
            client.post(
                internal, content=b"", headers={**headers, "X-AgentLens-Ingest-Key": "wrong-key"}
            ).status_code
            == 403
        )
        checks["malformed_protobuf_400"] = (
            client.post(internal, content=b"\xff", headers=internal_headers).status_code == 400
        )
        checks["unsupported_otlp_format_415"] = (
            client.post(
                internal,
                json={},
                headers={"X-AgentLens-Ingest-Key": settings.otlp_ingest_key.get_secret_value()},
            ).status_code
            == 415
        )
        checks["workbench_served"] = client.get("/workbench/").status_code == 200
    report = {
        "passed": all(checks.values()),
        "checks": checks,
        "paid_model_calls": 0,
        "business_quality_result": False,
        "probe_run_ids": [run["run_id"], other_id],
        "trace_id": run["trace_id"],
        "captured_sdk_spans": len(captured),
        "partial_spans": len(partial["spans"]),
        "final_spans": len(complete["spans"]),
    }
    (ROOT / "reports/week5-contracts.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    provider.shutdown()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    assert report["passed"], report


if __name__ == "__main__":
    main()
