"""One incident case, two real model configurations, one frozen data boundary."""

import json

import httpx
from sqlalchemy import select

from agentlens.config import ROOT, Settings
from agentlens.db import RunStep, create_session
from agentlens.executions import execution_difference
from agentlens.finops import cost_summary
from agentlens.security import mcp_headers


def test_one_case_two_real_model_configurations():
    settings = Settings()
    with httpx.Client(
        base_url="http://127.0.0.1:8000",
        trust_env=False,
        timeout=240,
        headers=mcp_headers(settings, "project-a"),
    ) as client:
        response = client.post(
            "/scenarios",
            json={
                "case_id": "pool-exhaustion-01",
                "source_run_id": "7d81edc0-496d-42ee-a739-77c0d98f2bd1",
            },
        )
        response.raise_for_status()
        scenario = response.json()
        results = []
        for model in ("agentlens-agent", "agentlens-candidate"):
            response = client.post(
                f"/scenarios/{scenario['scenario_id']}/evaluate", json={"model": model}
            )
            # Preserve provider errors and failed quality results in the artifact before assertions.
            event = response.json()
            run_id = event.get("run_id")
            if run_id:
                run = client.get(f"/runs/{run_id}").json()
                with create_session(settings) as session:
                    steps = session.scalars(select(RunStep).where(RunStep.run_id == run_id)).all()
                    cost = cost_summary(steps)
                difference = execution_difference(
                    settings, scenario["source_run_id"], run_id, "project-a"
                )
                results.append(
                    {
                        "model_alias": model,
                        "http_status": response.status_code,
                        "run": run,
                        "quality": difference["evaluation"]["candidate"],
                        "billing": cost,
                    }
                )
            else:
                results.append(
                    {"model_alias": model, "http_status": response.status_code, "error": event}
                )
        report = {
            "case_id": "pool-exhaustion-01",
            "selected_business_cases": 1,
            "model_driven_executions": len(results),
            "judge_requests": 0,
            "scenario_id": scenario["scenario_id"],
            "results": results,
        }
        report["passed"] = all(r["http_status"] == 200 and r["quality"]["passed"] for r in results)
        (ROOT / "reports/week89-acceptance.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        assert report["passed"], [
            (r["model_alias"], r["http_status"], r.get("quality")) for r in results
        ]
