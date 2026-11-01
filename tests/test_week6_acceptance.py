"""Exactly one new business execution; rescore the frozen failed run as its baseline."""

import asyncio
import json

from agentlens.config import ROOT, Settings
from agentlens.experiments import compare_reports, run_evaluation
from agentlens.gate import evaluate_gate


def test_one_case_with_rules_judge_and_quality_gate():
    directory = ROOT / "reports/experiments"
    dataset = ROOT / "datasets/week6/dev.jsonl"
    settings = Settings()

    async def experiment():
        baseline = await run_evaluation(
            settings,
            dataset,
            ["pool-exhaustion-01"],
            "week6-baseline",
            directory / "week6-baseline.json",
            recorded_file=ROOT / "reports/pgvector-acceptance.json",
            with_judge=True,
        )
        candidate = await run_evaluation(
            settings,
            dataset,
            ["pool-exhaustion-01"],
            "week6-candidate",
            directory / "week6-candidate.json",
            with_judge=True,
        )
        return baseline, candidate

    baseline, candidate = asyncio.run(experiment(), loop_factory=asyncio.SelectorEventLoop)
    assert baseline["summary"]["failed"] == 1
    assert baseline["cases"][0]["evaluation"]["failure_reasons"] == [
        "runbook_retrieved",
        "runbook_cited",
    ]
    comparison = compare_reports(
        directory / "week6-baseline.json", directory / "week6-candidate.json"
    )
    gate = evaluate_gate(
        directory / "week6-baseline.json",
        directory / "week6-candidate.json",
        ROOT / "configs/evaluation/gate.json",
    )
    report = {
        "selected_cases": 1,
        "new_business_runs": 1,
        "baseline_recorded_run_id": baseline["cases"][0]["run"]["run_id"],
        "candidate_run_id": candidate["cases"][0]["run"]["run_id"],
        "judge_assessments_requested": 2,
        "judge_is_advisory": True,
        "comparison": comparison,
        "gate": gate,
        "passed": candidate["summary"]["passed"] == 1 and gate["passed"],
    }
    (ROOT / "reports/week6-acceptance.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    assert candidate["summary"]["passed"] == 1, candidate["cases"][0]["evaluation"]
    assert candidate["summary"]["judge_errors"] == 0, candidate["cases"][0].get("judge")
    assert comparison["cases"][0]["change"] == "improved"
    assert gate["passed"], gate["failures"]
