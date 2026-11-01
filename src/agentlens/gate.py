import hashlib
import json
from pathlib import Path

from agentlens.experiments import compare_reports


def evaluate_gate(baseline: Path, candidate: Path, policy: Path) -> dict:
    comparison = compare_reports(baseline, candidate)
    config = json.loads(policy.read_text(encoding="utf-8"))
    report = json.loads(candidate.read_text(encoding="utf-8"))
    cases = {c["case_id"]: c for c in report["cases"]}
    failures = []
    for case_id in config["required_case_ids"]:
        case = cases.get(case_id)
        if case is None:
            failures.append({"case_id": case_id, "reason": "required_case_missing"})
        elif case["outcome"] != "passed":
            failures.append(
                {
                    "case_id": case_id,
                    "reason": case["outcome"],
                    "checks": (case["evaluation"] or {}).get("failure_reasons", []),
                }
            )
        elif config["require_judge"] and case.get("judge", {}).get("status") != "complete":
            failures.append({"case_id": case_id, "reason": "judge_missing_or_error"})
    if not report["summary"]["complete"]:
        failures.append({"reason": "experiment_incomplete"})
    for row in comparison["cases"]:
        if row["change"] in {"regressed", "mixed", "incomparable"}:
            failures.append(
                {
                    "case_id": row["case_id"],
                    "reason": row["change"],
                    "checks": row["regressed_checks"],
                }
            )
    return {
        "passed": not failures,
        "failures": failures,
        "comparison": comparison,
        "policy": config,
        "policy_sha256": hashlib.sha256(policy.read_bytes()).hexdigest(),
        "execution_kind": report.get("execution_kind", "recorded_or_live"),
        "judge_score_gate_enabled": False,
        "note": (
            "Judge scores are advisory pending genuine human calibration; no aggregate threshold"
        ),
    }
