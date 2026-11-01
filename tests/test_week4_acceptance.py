"""Exactly one synthetic fault case through real DeepSeek and a restarted API process."""

import json
import os
import re
import subprocess
import sys
import time

import httpx

from agentlens.config import ROOT
from agentlens.evaluation import evaluate, load_case


def stop_api(process):
    # The Windows venv launcher owns a second Python process; terminate the owned tree.
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"], check=True, capture_output=True
        )
    else:
        process.terminate()
    process.wait(timeout=10)


def start_api(log):
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "agentlens.api:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8020",
            "--loop",
            "agentlens.checkpoints:loop_factory",
        ],
        cwd=ROOT,
        stdout=log,
        stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONUTF8": "1"},
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    try:
        for _ in range(150):
            assert process.poll() is None, "Acceptance API exited; inspect data/week4-api.log"
            try:
                if (
                    httpx.get(
                        "http://127.0.0.1:8020/health", timeout=0.2, trust_env=False
                    ).status_code
                    == 200
                ):
                    return process
            except (httpx.ConnectError, httpx.TimeoutException):
                pass
            time.sleep(0.1)
        raise AssertionError("Acceptance API did not become ready")
    except BaseException:
        if process.poll() is None:
            stop_api(process)
        raise


def test_one_fault_checkpoint_confirmation_and_memory():
    case = load_case("pool-exhaustion-01")
    report = {
        "case_id": case["case_id"],
        "selected_cases": 1,
        "real_model": True,
        "pgvector_verified": False,
        "runs": [],
        "status": "incomplete",
    }
    target = ROOT / "reports/week4-acceptance.json"
    events = []
    process = None
    with (ROOT / "data/week4-api.log").open("w", encoding="utf-8") as log:
        try:
            process = start_api(log)
            first_pid = process.pid
            with httpx.Client(
                base_url="http://127.0.0.1:8020",
                timeout=120,
                headers={"X-AgentLens-Project": case["project_id"]},
                trust_env=False,
            ) as client:
                response = client.post("/threads")
                assert response.status_code == 201, response.text
                thread_id = response.json()["thread_id"]
                with client.stream(
                    "POST",
                    f"/threads/{thread_id}/runs?stream=true",
                    json={
                        "prompt": case["input"],
                        "experience": {
                            **{k: case[k] for k in ["service", "start_time", "end_time"]},
                            "applicability": "合成 order-api 连接池饱和演示；"
                            "慢 SQL、泄漏等深层原因尚未确认。",
                        },
                    },
                ) as response:
                    assert response.status_code == 200
                    for line in response.iter_lines():
                        if line.startswith("data: "):
                            events.append(json.loads(line[6:]))
                report["events"] = events
                assert events[-1]["event"] == "run_interrupted", events[-1]
                paused = events[-1]
                original = client.get(f"/runs/{paused['run_id']}").json()
                report["runs"].append(original)
                verdict = evaluate(case, original)
                report["diagnosis_evaluation"] = verdict
                assert verdict["passed"], verdict
                before = client.get("/experiences", params={"service": "order-api"}).json()
                assert not any(
                    r["origin_run_id"] == paused["run_id"] for r in before["experiences"]
                )
            # Resume in a different actual API process. The MCP and DB stay running.
            stop_api(process)
            process = start_api(log)
            assert process.pid != first_pid
            report["api_launcher_process_ids"] = [first_pid, process.pid]
            report["api_server_process_ids"] = re.findall(
                r"Started server process \[(\d+)\]",
                (ROOT / "data/week4-api.log").read_text(encoding="utf-8"),
            )
            assert len(set(report["api_server_process_ids"])) == 2
            with httpx.Client(
                base_url="http://127.0.0.1:8020",
                timeout=120,
                headers={"X-AgentLens-Project": case["project_id"]},
                trust_env=False,
            ) as client:
                state = client.get(f"/threads/{thread_id}").json()
                assert state["checkpoint_id"] == paused["checkpoint_id"]
                request = {"checkpoint_id": paused["checkpoint_id"], "approved": True}
                response = client.post(f"/threads/{thread_id}/resume", json=request)
                assert response.status_code == 200, response.text
                saved = response.json()
                assert saved["event"] == "run_finished" and saved["experience_id"]
                assert saved["usage"] == {"input_tokens": 0, "output_tokens": 0}
                resumed = client.get(f"/runs/{saved['run_id']}").json()
                report["runs"].append(resumed)
                assert resumed["source_run_id"] == original["run_id"]
                assert client.post(f"/threads/{thread_id}/resume", json=request).status_code == 409
                rows = client.get("/experiences", params={"service": "order-api"}).json()[
                    "experiences"
                ]
                assert len([r for r in rows if r["origin_run_id"] == original["run_id"]]) == 1
                response = client.post(
                    f"/threads/{thread_id}/runs",
                    json={
                        "prompt": "沿用上一轮故障调查的日志和指标，"
                        "简要说明已知事实与尚未证实的深层原因。"
                        "引用先前证据即可，无需重复查询，不要再次保存经验。",
                    },
                )
                assert response.status_code == 200, response.text
                followup = response.json()
                assert followup["event"] == "run_finished", followup
                followup_run = client.get(f"/runs/{followup['run_id']}").json()
                report["runs"].append(followup_run)
                assert set(followup["diagnosis"]["evidence_ids"]) & set(case["required_evidence"])
                first_model = next(s for s in followup_run["steps"] if s["kind"] == "model")
                assert len(first_model["input"]["messages"]) > 1
                new_thread = client.post("/threads").json()["thread_id"]
                response = client.post(
                    f"/threads/{new_thread}/runs",
                    json={
                        "prompt": "请先用 search_experiences 查询 order-api 经确认的历史故障经验，"
                        "说明适用条件与未知问题并引用经验 ID。这次只是历史查询，"
                        "没有新故障的时间窗与"
                        "现场遥测，请返回 insufficient_evidence，不能认定当前发生了相同故障。",
                    },
                )
                assert response.status_code == 200, response.text
                recalled = response.json()
                assert recalled["event"] == "run_finished", recalled
                recalled_run = client.get(f"/runs/{recalled['run_id']}").json()
                report["runs"].append(recalled_run)
                assert recalled["diagnosis"]["status"] == "insufficient_evidence"
                assert saved["experience_id"] in recalled["diagnosis"]["evidence_ids"]
                assert any(s["name"] == "search_experiences" for s in recalled_run["steps"])
            report.update(
                {
                    "status": "passed",
                    "thread_id": thread_id,
                    "new_thread_id": new_thread,
                    "experience_id": saved["experience_id"],
                    "api_restart_verified": True,
                    "approval_client": "automated acceptance of synthetic incident",
                    "total_usage": {
                        key: sum(run["usage"][key] for run in report["runs"])
                        for key in ["input_tokens", "output_tokens"]
                    },
                    "limitation": "One fault case, three model-driven turns and one model-free "
                    "resume; "
                    "structured experience retrieval only, no pgvector quality result.",
                }
            )
        finally:
            target.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            if process is not None and process.poll() is None:
                stop_api(process)
