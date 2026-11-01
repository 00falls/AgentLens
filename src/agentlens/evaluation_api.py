"""Serve locally generated experiment artifacts within the selected project scope."""

import json
from pathlib import Path

from agentlens.conversations import ConversationError
from agentlens.experiments import compare_reports


def report_path(directory: Path, name: str) -> Path:
    if (
        not name
        or len(name) > 80
        or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for c in name
        )
    ):
        raise ConversationError(422, "Invalid evaluation ID")
    path = directory / f"{name}.json"
    if not path.is_file():
        raise ConversationError(404, "Evaluation not found")
    return path


def scoped_report(path: Path, project: str) -> dict:
    report = json.loads(path.read_text(encoding="utf-8"))
    rows = [c for c in report["cases"] if c["run"]["project_id"] == project]
    if not rows:
        raise ConversationError(404, "Evaluation not found")
    passed = sum(c["outcome"] == "passed" for c in rows)
    failed = sum(c["outcome"] == "failed" for c in rows)
    errors = len(rows) - passed - failed
    judge_errors = sum(c.get("judge", {}).get("status") == "error" for c in rows)
    return {
        **report,
        "evaluation_id": path.stem,
        "cases": rows,
        "summary": {
            "selected": len(rows),
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "judge_errors": judge_errors,
            "complete": errors == 0 and judge_errors == 0,
            "pass_rate": passed / len(rows) if not errors and not judge_errors else None,
        },
    }


def list_evaluations(directory: Path, project: str) -> list[dict]:
    rows = []
    for path in sorted(directory.glob("*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        if not any(c["run"]["project_id"] == project for c in report["cases"]):
            continue
        scoped = scoped_report(path, project)
        rows.append(
            {
                "evaluation_id": path.stem,
                "name": scoped["name"],
                "summary": scoped["summary"],
                "recorded_run": scoped["recorded_run"],
                "finished_at": scoped["finished_at"],
                "dataset_name": scoped["dataset_name"],
            }
        )
    return rows


def scoped_comparison(directory: Path, baseline: str, candidate: str, project: str) -> dict:
    before, after = (report_path(directory, name) for name in [baseline, candidate])
    owned_before = {c["case_id"] for c in scoped_report(before, project)["cases"]}
    owned_after = {c["case_id"] for c in scoped_report(after, project)["cases"]}
    try:
        comparison = compare_reports(before, after)
    except ValueError as exc:
        raise ConversationError(409, str(exc)) from exc
    comparison["cases"] = [
        c
        for c in comparison["cases"]
        if c["case_id"] in owned_before & owned_after and c["project_id"] == project
    ]
    return comparison
