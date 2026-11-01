"""The single week-one acceptance case uses the real gateway, model and PostgreSQL."""

import asyncio
import json
import os
from importlib.metadata import version

from fastapi.testclient import TestClient

from agentlens.api import app
from agentlens.config import ROOT, Settings
from agentlens.db import create_session
from agentlens.evaluation import evaluate, load_case
from agentlens.seed import seed


def test_pool_exhaustion_end_to_end():
    settings = Settings()
    case = load_case("pool-exhaustion-01")
    with create_session(settings) as session:
        seed(session)

    with TestClient(
        app,
        raise_server_exceptions=False,
        backend_options={"loop_factory": asyncio.SelectorEventLoop},
        headers={"X-AgentLens-Project": case["project_id"]},
    ) as client:
        response = client.post(
            "/agent/invoke", json={"project_id": case["project_id"], "prompt": case["input"]}
        )
        assert response.status_code == 200, response.text
        run_response = client.get(f"/runs/{response.json()['run_id']}")
        assert run_response.status_code == 200
        run = run_response.json()

    evaluation = evaluate(case, run)
    # An outside-window row exists in the same project/service; it must not leak into evidence.
    tool_steps = [step for step in run["steps"] if step["kind"] == "tool"]
    evaluation["checks"]["outside_window_excluded"] = all(
        not row["evidence_id"].endswith("-outside")
        for step in tool_steps
        if step["output"] is not None
        for collection in step["output"].values()
        for row in collection
    )
    evaluation["checks"]["token_usage_recorded"] = (
        run["usage"]["input_tokens"] > 0 and run["usage"]["output_tokens"] > 0
    )
    evaluation["passed"] = all(evaluation["checks"].values())
    report = {
        "case_id": case["case_id"],
        "real_model": True,
        "model_transport": "streaming through configured gateway",
        "database": "PostgreSQL",
        "evaluation": evaluation,
        "dependencies": {
            name: version(name)
            for name in ["langgraph", "langchain-openai", "litellm", "sqlalchemy", "mcp"]
        },
        "run": run,
    }
    report_path = ROOT / os.environ.get("AGENTLENS_ACCEPTANCE_REPORT", "reports/local/week1.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    assert evaluation["passed"], evaluation
