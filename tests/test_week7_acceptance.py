"""One fault case, two explicit modes: strict replay stop and frozen-data evaluation."""

import asyncio
import json

from agentlens.agent import read_run
from agentlens.config import ROOT, Settings
from agentlens.db import create_session
from agentlens.executions import execute_recording, execute_scenario, execution_difference
from agentlens.frozen import read_scenario
from agentlens.observability import configure_tracing
from agentlens.recordings import read_recording
from agentlens.run_diff import write_difference


def test_one_failed_case_replay_and_frozen_evaluation():
    prerequisites = json.loads((ROOT / "reports/week7-components.json").read_text(encoding="utf-8"))
    settings = Settings()
    configure_tracing("agentlens-week7-acceptance")
    with create_session(settings) as session:
        recording = read_recording(session, prerequisites["recording_id"], "project-a")
        scenario = read_scenario(session, prerequisites["scenario_id"], "project-a")
    assert recording["source_run_id"] == scenario["source_run_id"]

    async def exercise():
        replay = await execute_recording(
            settings.model_copy(update={"mcp_url": "http://127.0.0.1:1/intentionally-unreachable"}),
            recording["recording_id"],
            "project-a",
        )
        frozen = await execute_scenario(settings, scenario["scenario_id"], "project-a")
        return replay, frozen

    replay_event, frozen_event = asyncio.run(exercise(), loop_factory=asyncio.SelectorEventLoop)
    source_id = recording["source_run_id"]
    replay_diff = execution_difference(settings, source_id, replay_event["run_id"], "project-a")
    frozen_diff = execution_difference(settings, source_id, frozen_event["run_id"], "project-a")
    write_difference(replay_diff, ROOT / "reports/week7-replay-difference.json")
    write_difference(frozen_diff, ROOT / "reports/week7-frozen-difference.json")
    with create_session(settings) as session:
        replay = read_run(session, replay_event["run_id"])
        frozen = read_run(session, frozen_event["run_id"])
    report = {
        "selected_business_cases": 1,
        "case_id": "pool-exhaustion-01",
        "model_driven_executions": 2,
        "judge_requests": 0,
        "source_run_id": source_id,
        "recording_id": recording["recording_id"],
        "scenario_id": scenario["scenario_id"],
        "replay": replay,
        "frozen": frozen,
        "checks": {
            "strict_replay_mismatch": replay["status"] == "replay_mismatch",
            "replay_model_called": replay["usage"]["input_tokens"] > 0,
            "replay_has_no_live_transport": replay["versions"]["tool_transport"]
            == "recorded/no-mcp",
            "replay_explains_stop": bool(replay["failure_detail"]),
            "new_runs_link_source": replay["source_run_id"] == frozen["source_run_id"] == source_id,
            "frozen_rules_passed": frozen_diff["evaluation"]["candidate"]["passed"],
            "frozen_has_snapshot_version": bool(frozen["versions"]["scenario_manifest"]["sha256"]),
            "source_failure_preserved": not frozen_diff["evaluation"]["baseline"]["passed"],
            "no_deterministic_claim": not replay_diff["deterministic_reproduction"],
        },
    }
    report["passed"] = all(report["checks"].values())
    (ROOT / "reports/week7-acceptance.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    assert report["passed"], report["checks"]
