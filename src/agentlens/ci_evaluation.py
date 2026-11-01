"""Fixed development subset, incremental evidence and an independent regression gate."""

import hashlib
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

from agentlens.config import ROOT
from agentlens.db import KnowledgeDocument, Run, create_session
from agentlens.eval_budget import EvaluationBudget, active_budget
from agentlens.experiments import compare_reports, evaluator_version, run_evaluation, write_report
from agentlens.knowledge import corpus
from agentlens.replay import digest
from agentlens.run_diff import locate_failures

SELECTION = ROOT / "configs/evaluation/ci-cases.json"
POLICY = ROOT / "configs/evaluation/ci-gate.json"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def selected_cases(selection=SELECTION):
    from agentlens.evaluation import load_cases

    manifest = json.loads(selection.read_text(encoding="utf-8"))
    dataset = ROOT / manifest["dataset"]
    ids = manifest["case_ids"]
    if len(ids) != 10 or len(set(ids)) != 10:
        raise ValueError("CI selection must contain exactly ten distinct cases")
    if sha(dataset) != manifest["dataset_sha256"]:
        raise ValueError("Development dataset changed; review the frozen selection")
    lookup = {case["case_id"]: case for case in load_cases(dataset)}
    cases = [lookup[key] for key in ids]
    if any(case["split"] != "dev" for case in cases):
        raise ValueError("CI must not select holdout cases")
    return dataset, cases


def classify_failures(case, run, evaluation):
    checks = evaluation["checks"] if evaluation else {}
    failed = {key for key, value in checks.items() if value is False}
    groups = {
        "tool_selection_or_order": {
            "required_tools",
            "trajectory_required_tools",
            "trajectory_forbidden_tools",
            "trajectory_order",
        },
        "arguments_or_scope": {
            "query_scope",
            "outside_window_excluded",
            "project_scope",
            "knowledge_project_scope",
            "trajectory_parameters",
        },
        "citation_missing_or_invalid": {"valid_citations", "required_evidence", "runbook_cited"},
        "root_cause_rules_unmet": {"status", "cause_terms"},
    }
    tags = [
        {"category": category, "checks": sorted(failed & names)}
        for category, names in groups.items()
        if failed & names
    ]
    if "runbook_retrieved" in failed:
        called = any(s["kind"] == "tool" and s["name"] == "search_runbooks" for s in run["steps"])
        tags.append(
            {
                "category": "runbook_not_recalled" if called else "runbook_not_queried",
                "checks": ["runbook_retrieved"],
            }
        )
    if run["status"] in {"failed", "cancelled", "running", "interrupted", "replay_mismatch"}:
        tags.append({"category": "execution_error", "checks": [], "error": run["error"]})
    tool_names = {
        "required_tools",
        "trajectory_required_tools",
        "trajectory_forbidden_tools",
        "trajectory_order",
        "query_scope",
        "trajectory_parameters",
    }
    for tag in tags:
        tag["locations"] = [
            {"run_id": run["run_id"], "field": "evaluation." + key} for key in tag["checks"]
        ]
        if set(tag["checks"]) & tool_names or tag["category"] == "execution_error":
            tag["locations"] += [
                {
                    "run_id": run["run_id"],
                    "step_sequence": s["sequence"],
                    "field": "error" if s["error"] else "input",
                }
                for s in run["steps"]
                if s["kind"] == "tool" or s["error"]
            ]
    return {
        "tags": tags,
        "facts": locate_failures(run, case),
        "note": "Observable checks; overlapping tags do not prove causes or hallucination.",
    }


def summarize(report, planned):
    cases = report["cases"]
    passed = sum(c["outcome"] == "passed" for c in cases)
    failed = sum(c["outcome"] == "failed" for c in cases)
    errors = sum(c["outcome"] == "execution_error" for c in cases)
    complete = (
        len(cases) == planned
        and not errors
        and not report.get("batch_error")
        and not report.get("in_progress_case_id")
    )
    report["summary"] = {
        "selected": planned,
        "attempted": len(cases),
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "judge_errors": 0,
        "not_executed": planned - len(cases),
        "complete": complete,
        "coverage": len(cases) / planned,
        "pass_rate": passed / planned if complete else None,
        "confirmed_passed_of_planned": f"{passed}/{planned}",
    }
    families = {}
    for item in cases:
        family = families.setdefault(item["scenario_group"], Counter())
        family["attempted"] += 1
        family[item["outcome"]] += 1
    report["by_family"] = {k: dict(v) for k, v in families.items()}
    report["failure_categories"] = dict(
        Counter(tag["category"] for c in cases for tag in c["failure_analysis"]["tags"])
    )


def write_ci_report(report, target):
    write_report(report, target)
    lines = [
        "",
        "## Frozen experiment",
        "",
        f"Prompt: `{report['prompt_sha256']}`; commit: `{report['git_commit']}`.",
        f"Evaluator: `{report['evaluator_sha256']}`; dataset: `{report['dataset_sha256']}`.",
        f"Budget: `{json.dumps(report['budget'])}`.",
        "",
        "| Family | Attempted | Passed | Quality failed | Execution errors |",
        "|---|---:|---:|---:|---:|",
    ]
    for family, counts in report["by_family"].items():
        lines.append(
            f"| {family} | {counts['attempted']} | {counts.get('passed', 0)} "
            f"| {counts.get('failed', 0)} | {counts.get('execution_error', 0)} |"
        )
    lines += [
        "",
        "## Failure categories",
        "",
        "Counts may overlap; these are observable rule failures, not causal claims.",
        "",
    ]
    lines += [f"- {category}: {count}" for category, count in report["failure_categories"].items()]
    lines += ["", f"Not executed: {report['not_executed_case_ids']}."]
    with target.with_suffix(".md").open("a", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")


async def run_ci_evaluation(settings, target, name="dev10", selection=SELECTION):
    if target.exists():
        raise ValueError(
            "Use a new report path; completed or partial evidence is never overwritten"
        )
    if (
        settings.model != "agentlens-agent"
        or settings.configured_upstream_model != "openai/deepseek-flash"
    ):
        raise ValueError("This campaign is frozen to the Flash gateway configuration")
    dataset, cases = selected_cases(selection)
    with create_session(settings) as session:
        if session.scalar(select(func.count()).select_from(Run)):
            raise ValueError(
                "Use a clean evaluation database, not the existing application database"
            )
        if session.scalar(
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(KnowledgeDocument.kind != "runbook")
        ):
            raise ValueError("Evaluation data must not contain historical incident experience")
    policy = json.loads(POLICY.read_text())
    budget = EvaluationBudget(Decimal(policy["batch_budget_usd"]))
    _, _, knowledge = corpus()
    artifact = json.loads((settings.embedding_path / "artifacts.json").read_text())
    git = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, encoding="utf-8"
    )
    contract = {
        "selection_sha256": sha(selection),
        "dataset_sha256": sha(dataset),
        "telemetry_sha256": [
            sha(ROOT / p) for p in ["datasets/telemetry.json", "datasets/week6/telemetry.json"]
        ],
        "knowledge": knowledge,
        "embedding_artifacts": digest(artifact),
        "model": settings.configured_upstream_model,
        "max_model_calls": settings.max_model_calls,
        "max_output_tokens": settings.max_output_tokens,
        "temperature": 0,
        "thinking": "disabled",
    }
    report = {
        "schema_version": 2,
        "name": name,
        "started_at": datetime.now(UTC).isoformat(),
        "finished_at": None,
        "dataset_sha256": sha(dataset),
        "dataset_name": dataset.name,
        "evaluator_sha256": evaluator_version(),
        "judge_config": None,
        "recorded_run": False,
        "execution_kind": "live_flash_dev10",
        "contract": contract,
        "selection": [case["case_id"] for case in cases],
        "cases": [],
        "prompt_sha256": sha(ROOT / "prompts/diagnose.md"),
        "git_commit": git.stdout.strip() if git.returncode == 0 else None,
        "source_sha256": {
            p: sha(ROOT / "src/agentlens" / p)
            for p in ["graph.py", "agent.py", "mcp_server.py", "ci_evaluation.py", "eval_budget.py"]
        },
        "batch_error": None,
        "in_progress_case_id": None,
    }
    token = active_budget.set(budget)

    def persist():
        catalogs = {c["run"]["versions"].get("tool_schemas_sha256") for c in report["cases"]}
        report["contract"]["tool_catalog_sha256"] = sorted(c for c in catalogs if c is not None)
        report["budget"] = {
            "limit_usd": str(budget.limit),
            "known_spent_usd": str(budget.spent),
            "model_calls": budget.calls,
            "unknown_usage": budget.unknown_usage,
            "note": "Conservative application-side reserve; not a provider billing cap.",
        }
        summarize(report, len(cases))
        report["not_executed_case_ids"] = [c["case_id"] for c in cases[len(report["cases"]) :]]
        write_ci_report(report, target)

    persist()
    try:
        for case in cases:
            if budget.spent >= budget.limit or budget.unknown_usage:
                report["batch_error"] = "Budget exhausted or previous call's usage is unknown"
                break
            report["in_progress_case_id"] = case["case_id"]
            persist()
            result = await run_evaluation(
                settings,
                dataset,
                [case["case_id"]],
                name,
                target.parent / (target.stem + "-cases") / (case["case_id"] + ".json"),
            )
            item = result["cases"][0]
            item["failure_analysis"] = classify_failures(case, item["run"], item["evaluation"])
            report["cases"].append(item)
            report["in_progress_case_id"] = None
            print(
                json.dumps(
                    {
                        "case_id": case["case_id"],
                        "outcome": item["outcome"],
                        "spent_usd": str(budget.spent),
                    }
                ),
                flush=True,
            )
            if item["outcome"] == "execution_error":
                missing = any(
                    s["kind"] == "model" and not s["output"] for s in item["run"]["steps"]
                )
                if missing:
                    budget.unknown_usage = True
                if missing or "BudgetStop" in (item["error"] or ""):
                    report["batch_error"] = item["error"]
            persist()
            if report["batch_error"]:
                break
    except BaseException as exc:
        report["batch_error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        active_budget.reset(token)
        report["finished_at"] = datetime.now(UTC).isoformat()
        persist()
    return report


def evaluate_ci_gate(baseline_path, candidate_path, policy=POLICY, selection=SELECTION):
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    config = json.loads(policy.read_text())
    _, expected = selected_cases(selection)
    expected_ids = {c["case_id"] for c in expected}
    failures = []
    for label, report in [("baseline", baseline), ("candidate", candidate)]:
        ids = [c["case_id"] for c in report["cases"]]
        if len(ids) != 10 or set(ids) != expected_ids:
            failures.append({"reason": "missing_or_duplicate_cases", "report": label})
        if not report["summary"]["complete"] or report.get("batch_error"):
            failures.append({"reason": "experiment_incomplete", "report": label})
        if any(c["outcome"] == "execution_error" for c in report["cases"]):
            failures.append({"reason": "execution_error", "report": label})
    if baseline.get("contract") != candidate.get("contract"):
        failures.append({"reason": "experiment_contract_changed"})
    try:
        comparison = compare_reports(baseline_path, candidate_path)
    except ValueError as exc:
        failures.append({"reason": "incomparable", "detail": str(exc)})
        comparison = None
    before = {c["case_id"]: c for c in baseline["cases"]}
    after = {c["case_id"]: c for c in candidate["cases"]}
    for case_id in config["required_case_ids"]:
        if after.get(case_id, {}).get("outcome") != "passed":
            failures.append({"reason": "critical_case_not_passed", "case_id": case_id})
    for case_id, previous in before.items():
        if previous["outcome"] == "passed" and after.get(case_id, {}).get("outcome") != "passed":
            failures.append({"reason": "previously_passed_case_regressed", "case_id": case_id})
    if sum(c["outcome"] == "passed" for c in after.values()) < sum(
        c["outcome"] == "passed" for c in before.values()
    ):
        failures.append({"reason": "aggregate_pass_rate_decreased"})
    return {
        "passed": not failures,
        "failures": failures,
        "comparison": comparison,
        "policy": config,
        "policy_sha256": sha(policy),
        "judge_used": False,
    }
