import hashlib
import json
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from agentlens.agent import InvestigationFailed, investigate, read_run
from agentlens.config import Settings
from agentlens.db import create_session
from agentlens.evaluation import evaluate, load_cases
from agentlens.judge import judge_run, judge_version


def evaluator_version() -> str:
    files = ["evaluation.py", "experiments.py", "trajectory.py", "schemas.py", "judge.py"]
    return hashlib.sha256(
        b"".join(Path(__file__).with_name(f).read_bytes() for f in files)
        + version("agentevals").encode()
    ).hexdigest()


def select_cases(dataset: Path, case_ids: list[str] | None) -> list[dict]:
    cases = load_cases(dataset)
    if case_ids is not None:
        unknown = set(case_ids) - {case["case_id"] for case in cases}
        if unknown:
            raise ValueError(f"Unknown case IDs: {sorted(unknown)}")
        cases = [case for case in cases if case["case_id"] in case_ids]
    if not cases:
        raise ValueError("No evaluation cases selected")
    return cases


def write_report(report: dict, target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        f"# {report['name']}",
        "",
        f"Summary: {json.dumps(report['summary'])}",
        "",
        "| Case | Outcome | Run | Failed checks |",
        "|---|---|---|---|",
    ]
    for result in report["cases"]:
        reason = (
            result["error"]
            if result["evaluation"] is None
            else ", ".join(result["evaluation"]["failure_reasons"])
        )
        lines.append(
            f"| {result['case_id']} | {result['outcome']} | {result['run']['run_id']} "
            f"| {reason.replace('|', '/').replace(chr(10), ' ')} |"
        )
    target.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")


async def run_evaluation(
    settings: Settings,
    dataset: Path,
    case_ids: list[str] | None,
    name: str,
    target: Path,
    recorded_run_id: str | None = None,
    with_judge: bool = False,
    recorded_file: Path | None = None,
) -> dict:
    cases = select_cases(dataset, case_ids)
    if (recorded_run_id is not None or recorded_file is not None) and len(cases) != 1:
        raise ValueError("Recorded evaluation requires exactly one selected case")
    results = []
    started_at = datetime.now(UTC).isoformat()
    for case in cases:
        run_id = recorded_run_id
        if run_id is None and recorded_file is None:
            try:
                result = await investigate(settings, case["project_id"], case["input"])
                run_id = result["run_id"]
            except InvestigationFailed as exc:
                run_id = exc.run_id
        if recorded_file is not None:
            run = json.loads(recorded_file.read_text(encoding="utf-8"))["run"]
        else:
            with create_session(settings) as session:
                run = read_run(session, run_id)
        if run is None:
            raise ValueError(f"Run not found: {run_id}")
        if run["project_id"] != case["project_id"] or run["input"] != case["input"]:
            raise ValueError(f"Run {run_id} does not belong to case {case['case_id']}")
        execution_error = run["status"] in {
            "failed",
            "cancelled",
            "running",
            "interrupted",
            "replay_mismatch",
        }
        evaluation = None if execution_error else evaluate(case, run)
        outcome = (
            "execution_error"
            if execution_error
            else ("passed" if evaluation["passed"] else "failed")
        )
        results.append(
            {
                "case_id": case["case_id"],
                "critical": case["critical"],
                "scenario_group": case["scenario_group"],
                "split": case["split"],
                "outcome": outcome,
                "evaluation": evaluation,
                "error": (run["error"] or f"Run is not complete: {run['status']}")
                if execution_error
                else None,
                "run": run,
            }
        )
        if with_judge and not execution_error:
            try:
                results[-1]["judge"] = await judge_run(settings, case["input"], run)
            except Exception as exc:
                # Preserve the completed business run and make the failed assessment explicit.
                results[-1]["judge"] = {
                    "status": "error",
                    "error": str(exc),
                    "version": judge_version(settings),
                }
    passed = sum(result["outcome"] == "passed" for result in results)
    failed = sum(result["outcome"] == "failed" for result in results)
    errors = len(results) - passed - failed
    judge_errors = sum(r.get("judge", {}).get("status") == "error" for r in results)
    report = {
        "schema_version": 2,
        "name": name,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "evaluator_sha256": evaluator_version(),
        "agentevals_version": version("agentevals"),
        "dataset_name": dataset.name,
        "judge_config": judge_version(settings) if with_judge else None,
        "recorded_run": recorded_run_id is not None or recorded_file is not None,
        "summary": {
            "selected": len(cases),
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "judge_errors": judge_errors,
            "complete": errors == 0 and judge_errors == 0,
            "pass_rate": passed / len(cases) if errors == 0 and judge_errors == 0 else None,
        },
        "cases": results,
    }
    write_report(report, target)
    return report


def compare_reports(baseline_path: Path, candidate_path: Path) -> dict:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    for key in ["schema_version", "dataset_sha256", "evaluator_sha256"]:
        if baseline[key] != candidate[key]:
            raise ValueError(f"Reports have different {key}; evaluate using the same contract")
    before = {item["case_id"]: item for item in baseline["cases"]}
    after = {item["case_id"]: item for item in candidate["cases"]}
    if before.keys() != after.keys():
        raise ValueError("Comparison requires the same selected case IDs")
    differences = []
    for case_id, previous in before.items():
        current = after[case_id]
        if "execution_error" in {previous["outcome"], current["outcome"]}:
            change = "incomparable"
        elif previous["outcome"] == current["outcome"]:
            change = "unchanged"
        else:
            change = "improved" if current["outcome"] == "passed" else "regressed"
        differences.append(
            {
                "case_id": case_id,
                "change": change,
                "baseline_outcome": previous["outcome"],
                "candidate_outcome": current["outcome"],
                "baseline_run_id": previous["run"]["run_id"],
                "candidate_run_id": current["run"]["run_id"],
                "project_id": current["run"]["project_id"],
                "baseline_checks": previous["evaluation"]["checks"]
                if previous["evaluation"]
                else {},
                "candidate_checks": current["evaluation"]["checks"]
                if current["evaluation"]
                else {},
                "baseline_dimensions": previous["evaluation"].get("dimensions", {})
                if previous["evaluation"]
                else {},
                "candidate_dimensions": current["evaluation"].get("dimensions", {})
                if current["evaluation"]
                else {},
                "baseline_judge": previous.get("judge"),
                "candidate_judge": current.get("judge"),
                "baseline_cause": (previous["run"]["output"] or {}).get("cause_summary"),
                "candidate_cause": (current["run"]["output"] or {}).get("cause_summary"),
                "input_token_delta": (
                    current["run"]["usage"]["input_tokens"]
                    - previous["run"]["usage"]["input_tokens"]
                ),
                "output_token_delta": (
                    current["run"]["usage"]["output_tokens"]
                    - previous["run"]["usage"]["output_tokens"]
                ),
            }
        )
        item = differences[-1]
        all_checks = item["baseline_checks"].keys() | item["candidate_checks"].keys()
        item["improved_checks"] = [
            k
            for k in sorted(all_checks)
            if item["baseline_checks"].get(k) is False and item["candidate_checks"].get(k) is True
        ]
        item["regressed_checks"] = [
            k
            for k in sorted(all_checks)
            if item["baseline_checks"].get(k) is True and item["candidate_checks"].get(k) is False
        ]
        if change != "incomparable":
            item["change"] = (
                "mixed"
                if item["improved_checks"] and item["regressed_checks"]
                else "improved"
                if item["improved_checks"]
                else "regressed"
                if item["regressed_checks"]
                else change
            )
    return {"baseline": baseline["name"], "candidate": candidate["name"], "cases": differences}
