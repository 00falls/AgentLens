"""Exactly one real-model case over real HTTP SSE, MCP and PostgreSQL."""

import json
import os
import subprocess
import sys
from time import perf_counter

import httpx

from agentlens.config import ROOT
from agentlens.evaluation import evaluate, load_case


def test_pool_exhaustion_sse_and_mcp():
    case = load_case("pool-exhaustion-01")
    events = []
    started = perf_counter()
    base_url = os.environ.get("AGENTLENS_ACCEPTANCE_URL", "http://127.0.0.1:8000")
    with httpx.Client(
        base_url=base_url, timeout=90, headers={"X-AgentLens-Project": case["project_id"]}
    ) as client:
        with client.stream(
            "POST",
            "/agent/stream",
            json={"project_id": case["project_id"], "prompt": case["input"]},
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            event_name = None
            for line in response.iter_lines():
                if line.startswith("event: "):
                    event_name = line[7:]
                elif line.startswith("data: "):
                    event = json.loads(line[6:])
                    assert event["event"] == event_name
                    events.append({**event, "received_after_seconds": perf_counter() - started})
                    if event_name == "run_started":
                        running = client.get(f"/runs/{event['run_id']}")
                        assert running.status_code == 200
                        assert running.json()["status"] == "running"
        assert events[0]["event"] == "run_started"
        assert events[-1]["event"] == "run_finished", events[-1]
        assert any(event["event"] == "answer_delta" for event in events)
        assert events[0]["received_after_seconds"] < events[-1]["received_after_seconds"]
        run = client.get(f"/runs/{events[-1]['run_id']}").json()

    verdict = evaluate(case, run)
    assert verdict["passed"], verdict
    assert run["versions"]["tool_transport"] == "mcp/streamable-http"
    assert run["versions"]["tool_schemas_sha256"]
    started_steps = [event["step"] for event in events if event["event"] == "step_started"]
    finished_steps = [event["step"] for event in events if event["event"] == "step_finished"]
    assert started_steps == finished_steps == [step["sequence"] for step in run["steps"]]
    assert all(event["run_id"] == run["run_id"] for event in events)

    report = {
        "case_id": case["case_id"],
        "real_model": True,
        "real_http_sse": True,
        "evaluation": verdict,
        "events": events,
        "run": run,
    }
    target = ROOT / "reports/week2-acceptance.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Exercise the CLI by rescoring this exact run; no second model invocation.
    command = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentlens.cli",
            "eval",
            "--case",
            case["case_id"],
            "--recorded-run",
            run["run_id"],
            "--name",
            "week2-mcp-sse",
            "--report",
            str(ROOT / "reports/week2-evaluation.json"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1"},
        timeout=30,
    )
    assert command.returncode == 0, command.stdout + command.stderr
    batch = json.loads((ROOT / "reports/week2-evaluation.json").read_text(encoding="utf-8"))
    assert batch["recorded_run"] is True
    assert batch["summary"] == {
        "selected": 1,
        "passed": 1,
        "failed": 0,
        "errors": 0,
        "complete": True,
        "pass_rate": 1.0,
    }
