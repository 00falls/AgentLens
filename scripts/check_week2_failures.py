"""Check lifecycle failures with real PG/MCP and a replaced external model. No paid calls."""

import asyncio
import json
import threading
import time
from unittest.mock import patch

import httpx
import uvicorn
from langchain_core.messages import AIMessageChunk

from agentlens.agent import investigation_events, read_run
from agentlens.api import app
from agentlens.config import ROOT, Settings
from agentlens.db import create_session

TARGET = ROOT / "reports/local/lifecycle-checks.json"


class FailingProvider:
    def bind_tools(self, tools):
        return self

    async def astream(self, messages):
        yield AIMessageChunk(content="")
        raise RuntimeError("controlled_provider_failure")


class WaitingProvider:
    def bind_tools(self, tools):
        return self

    async def astream(self, messages):
        yield AIMessageChunk(content="")
        await asyncio.Event().wait()


async def check():
    settings = Settings()
    with patch("agentlens.graph.ChatOpenAI", return_value=FailingProvider()):
        events = [
            event
            async for event in investigation_events(
                settings, "project-a", "Controlled model failure probe; not a diagnosis case"
            )
        ]
    assert events[-1]["event"] == "run_failed", events
    with create_session(settings) as session:
        failed = read_run(session, events[-1]["run_id"])
    assert failed["status"] == "failed"
    assert "controlled_provider_failure" in failed["error"]
    assert failed["steps"][-1]["error"] is not None

    with patch("agentlens.graph.ChatOpenAI", return_value=WaitingProvider()):
        stream = investigation_events(settings, "project-a", "Controlled stream-close probe")
        started = await anext(stream)
        step = await anext(stream)
        assert step["event"] == "step_started", step
        await stream.aclose()
    with create_session(settings) as session:
        cancelled = read_run(session, started["run_id"])
    assert cancelled["status"] == "cancelled", cancelled
    assert cancelled["finished_at"] is not None
    report = {
        "model_calls": 0,
        "checks": {
            "model_failure_persisted": True,
            "failure_event": True,
            "generator_close_persisted_as_cancelled": True,
        },
        "probe_run_ids": [failed["run_id"], cancelled["run_id"]],
    }
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


def check_http_lifecycle():
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=8012,
            log_level="warning",
            loop="agentlens.checkpoints:loop_factory",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started, "Lifecycle probe HTTP server did not start"
        with httpx.Client(
            base_url="http://127.0.0.1:8012",
            timeout=15,
            headers={"X-AgentLens-Project": "project-a"},
        ) as client:
            with patch("agentlens.graph.ChatOpenAI", return_value=FailingProvider()):
                response = client.post(
                    "/agent/invoke",
                    json={
                        "project_id": "project-a",
                        "prompt": "Controlled HTTP provider failure probe",
                    },
                )
                assert response.status_code == 502, response.text
                failed_id = response.json()["run_id"]
                assert client.get(f"/runs/{failed_id}").json()["status"] == "failed"
            with patch("agentlens.graph.ChatOpenAI", return_value=WaitingProvider()):
                with client.stream(
                    "POST",
                    "/agent/stream",
                    json={"project_id": "project-a", "prompt": "Controlled HTTP disconnect probe"},
                ) as response:
                    for line in response.iter_lines():
                        if line.startswith("data: "):
                            event = json.loads(line[6:])
                            if event["event"] == "run_started":
                                run_id = event["run_id"]
                            if event["event"] == "step_started":
                                break
                # Closing a real socket must cancel the pending model call and persist its run.
                for _ in range(100):
                    cancelled = client.get(f"/runs/{run_id}").json()
                    if cancelled["status"] != "running":
                        break
                    time.sleep(0.05)
                assert cancelled["status"] == "cancelled", cancelled
        target = TARGET
        report = json.loads(target.read_text(encoding="utf-8"))
        report["checks"].update(
            {"http_failure_returns_502": True, "http_disconnect_persisted_as_cancelled": True}
        )
        report["probe_run_ids"].extend([failed_id, run_id])
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("HTTP 502 and socket-disconnect checks passed; provider requests: 0")
    finally:
        server.should_exit = True
        thread.join(timeout=5)


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(check(), timeout=20), loop_factory=asyncio.SelectorEventLoop)
    check_http_lifecycle()
