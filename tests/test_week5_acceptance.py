"""Exactly one real diagnosis through the complete OTel -> Collector -> PG pipeline."""

import json
import time

import httpx

from agentlens.config import ROOT
from agentlens.evaluation import evaluate, load_case


def test_one_fault_with_distributed_trace():
    case = load_case("pool-exhaustion-01")
    target = ROOT / "reports/week5-acceptance.json"
    report = {
        "case_id": case["case_id"],
        "selected_cases": 1,
        "real_model": True,
        "status": "incomplete",
        "pgvector_verified": False,
    }
    events = []
    try:
        with httpx.Client(
            base_url="http://127.0.0.1:8000",
            timeout=120,
            trust_env=False,
            headers={"X-AgentLens-Project": case["project_id"]},
        ) as client:
            created = client.post("/threads")
            assert created.status_code == 201
            thread_id = created.json()["thread_id"]
            with client.stream(
                "POST",
                f"/threads/{thread_id}/runs?stream=true",
                json={
                    "prompt": case["input"],
                },
            ) as response:
                assert response.status_code == 200
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        events.append(json.loads(line[6:]))
            report["events"] = events
            assert events[-1]["event"] == "run_finished", events[-1]
            run = client.get(f"/runs/{events[-1]['run_id']}").json()
            report["run"] = run
            verdict = evaluate(case, run)
            report["evaluation"] = verdict
            assert verdict["passed"], verdict
            assert run["trace_id"] == events[0]["trace_id"]
            assert run["checkpoint_id"] and run["thread_id"] and run["span_id"]
            expected_steps = {step["span_id"] for step in run["steps"]}
            trace_path = f"/traces/{run['trace_id']}?run_id={run['run_id']}"
            for _ in range(100):
                trace = client.get(trace_path).json()
                span_ids = {s["span_id"] for s in trace["spans"]}
                if (
                    trace["request_span_received"]
                    and expected_steps <= span_ids
                    and any(
                        s["resource"].get("service.name") == "agentlens-mcp" for s in trace["spans"]
                    )
                ):
                    break
                time.sleep(0.1)
            report["trace"] = trace
            assert trace["request_span_received"] and expected_steps <= span_ids
            assert run["span_id"] in span_ids and None not in expected_steps
            assert any(s["kind"] == "SPAN_KIND_SERVER" for s in trace["spans"])
            assert any(
                s["scope"] == "opentelemetry.instrumentation.openai_v2" for s in trace["spans"]
            )
            assert any(s["scope"] == "opentelemetry.instrumentation.httpx" for s in trace["spans"])
            assert any(s["resource"].get("service.name") == "agentlens-mcp" for s in trace["spans"])
            assert all(
                s["parent_span_id"] is None or s["parent_span_id"] in span_ids
                for s in trace["spans"]
            )
            listed = client.get(f"/runs?thread_id={run['thread_id']}").json()
            assert run["run_id"] in {row["run_id"] for row in listed["runs"]}
            assert (
                client.get(trace_path, headers={"X-AgentLens-Project": "project-b"}).status_code
                == 404
            )
            assert client.get("/workbench/").status_code == 200
            report["status"] = "passed"
    finally:
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
