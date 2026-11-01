"""Real PostgreSQL and API boundaries; provider-free component verification."""

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families
from sqlalchemy import select

from agentlens.api import app
from agentlens.config import ROOT, Settings
from agentlens.db import AuditEvent, Run, create_session
from agentlens.finops import gateway_model, price_call
from agentlens.operations import operation_summary, prometheus_export
from agentlens.sandbox import SandboxUnavailable, authorized_logs, execute_analysis
from agentlens.schemas import AnalysisQuery

SOURCE = "7d81edc0-496d-42ee-a739-77c0d98f2bd1"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as client:
        yield client


def headers(project="project-a"):
    keys = json.loads(Settings().identity_path.read_text(encoding="utf-8"))["local_cli"]
    return {"Authorization": f"Bearer {keys[project]}"}


def test_unauthenticated_and_body_project_cannot_bypass(client):
    assert client.get("/runs").status_code == 401
    assert client.get("/runs", headers={"Authorization": "Bearer invalid"}).status_code == 401
    for path in ("/agent/invoke", "/agent/stream"):
        r = client.post(path, headers=headers(), json={"project_id": "project-b", "prompt": "x"})
        assert r.status_code == 403


def test_header_project_cannot_override_key(client):
    for path in ("/runs", "/recordings", "/scenarios", "/audit-events", "/metrics"):
        assert (
            client.get(path, headers={**headers(), "X-AgentLens-Project": "project-b"}).status_code
            == 403
        )


def test_foreign_run_checkpoint_and_trace_are_not_readable(client):
    with create_session(Settings()) as session:
        run = session.get(Run, SOURCE)
        thread_id, trace_id = run.thread_id, run.trace_id
    for path in (f"/runs/{SOURCE}", f"/threads/{thread_id}", f"/traces/{trace_id}?run_id={SOURCE}"):
        assert client.get(path, headers=headers("project-b")).status_code == 404
    assert (
        client.post(
            f"/threads/{thread_id}/resume",
            headers=headers("project-b"),
            json={"checkpoint_id": "foreign", "approved": True},
        ).status_code
        == 404
    )


def test_two_identities_are_project_bound_and_audit_scoped(client):
    for project in ("project-a", "project-b"):
        r = client.get("/identity", headers=headers(project))
        assert r.json()["project"] == project
    with create_session(Settings()) as session:
        denied = session.scalars(select(AuditEvent).where(AuditEvent.decision == "deny")).all()
        assert any(e.actor == "demo-project-a" and e.result == "403" for e in denied)
    events = client.get("/audit-events", headers=headers()).json()["events"]
    assert all(e["actor"] != "demo-project-b" for e in events)


def test_analysis_only_accepts_logs_retrieved_by_same_authorized_run():
    request = AnalysisQuery(
        evidence_ids=["pool-exhaustion-log-1"], python_code="print(json.dumps({'count':len(logs)}))"
    )
    logs = authorized_logs(Settings(), "project-a", SOURCE, request)
    assert logs[0]["evidence_id"] == "pool-exhaustion-log-1"
    with pytest.raises(ValueError, match="authorized project"):
        authorized_logs(Settings(), "project-b", SOURCE, request)
    with pytest.raises(ValueError, match="already retrieved"):
        authorized_logs(
            Settings(),
            "project-a",
            SOURCE,
            request.model_copy(update={"evidence_ids": ["foreign-log"]}),
        )


def test_missing_runtime_never_executes_generated_code(tmp_path):
    settings = Settings(openshell_binary="agentlens-nonexistent-openshell")
    target = tmp_path / "must-not-exist"
    with pytest.raises(SandboxUnavailable):
        execute_analysis(settings, [], f"open({str(target)!r}, 'w').write('bad')")
    assert not target.exists()


def test_real_prometheus_export_uses_bounded_labels_and_ledger_counts(client):
    with create_session(Settings()) as session:
        export = prometheus_export(session, "project-a").decode()
        summary = operation_summary(session, "project-a")
    families = list(text_string_to_metric_families(export))
    samples = [s for f in families for s in f.samples]
    assert not any({"project_id", "run_id", "trace_id"} & s.labels.keys() for s in samples)
    assert (
        sum(
            s.value
            for s in samples
            if s.name == "agentlens_model_tokens_total" and s.labels["direction"] == "input"
        )
        == summary["input_tokens"]
    )
    assert summary["billing"]["total"] is None  # Historic records have no billing snapshot.
    assert summary["billing"]["unknown_calls"] > 0
    assert client.get("/metrics", headers=headers()).status_code == 200


def test_price_cache_and_unknowns_are_not_silently_zero():
    timestamp = datetime(2026, 11, 1, tzinfo=UTC)
    usage = {"input_tokens": 1000, "output_tokens": 100, "input_token_details": {"cache_read": 500}}
    p = price_call(usage, "deepseek-flash", timestamp)
    expected = (
        Decimal(500) * Decimal(".003")
        + Decimal(500) * Decimal(".15")
        + Decimal(100) * Decimal(".6")
    ) / Decimal(1000000)
    assert Decimal(p["cost"]) == expected
    assert p["cache_read_tokens"] == 500
    assert price_call(usage, "unknown", timestamp)["cost"] is None
    configured = gateway_model(Settings())
    assert price_call(usage, Settings().model, timestamp, configured)["cost"] is not None
    assert price_call(usage, "different-unverified-model", timestamp, configured)["cost"] is None
    assert (
        price_call({"input_tokens": 1000, "output_tokens": 100}, "deepseek-flash", timestamp)[
            "cost"
        ]
        is None
    )
    assert price_call(usage, "deepseek-flash", datetime(2026, 10, 30, tzinfo=UTC))["cost"] is None
    with pytest.raises(ValueError, match="exceed"):
        price_call(
            {**usage, "input_token_details": {"cache_read": 1001}}, "deepseek-flash", timestamp
        )


def test_delivery_does_not_contain_local_identity_keys():
    keys = json.loads(Settings().identity_path.read_text(encoding="utf-8"))["local_cli"]
    for path in (ROOT / "reports").glob("week[89]*"):
        if path.is_file():
            assert all(key.encode() not in path.read_bytes() for key in keys.values())
