from datetime import datetime

from agentlens.config import ROOT
from agentlens.schemas import EvaluationCase
from agentlens.trajectory import evaluate_trajectory


def load_cases(dataset=ROOT / "datasets/dev.jsonl") -> list[dict]:
    cases = [
        EvaluationCase.model_validate_json(line).model_dump(mode="json")
        for line in dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ids = [case["case_id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Dataset case_id values must be unique")
    return cases


def load_case(case_id: str) -> dict:
    for case in load_cases():
        if case["case_id"] == case_id:
            return case
    raise ValueError(f"Unknown case_id: {case_id}")


def evaluate(case: dict, run: dict) -> dict:
    case = EvaluationCase.model_validate(case).model_dump(mode="json")
    tool_steps = [step for step in run["steps"] if step["kind"] == "tool"]
    telemetry_steps = [
        step for step in tool_steps if step["name"] in {"search_logs", "query_metrics"}
    ]
    diagnosis = run["output"]
    if diagnosis is None:
        return {
            "passed": False,
            "checks": {"run_completed": False},
            "failure_reasons": ["run_completed"],
            "error": run["error"],
            "dimensions": {"task_completion": False},
        }
    tool_names = {step["name"] for step in tool_steps}
    retrieved_ids = {
        row["evidence_id"]
        for step in tool_steps
        if step["output"] is not None
        for collection in step["output"].values()
        for row in collection
    }
    start = datetime.fromisoformat(case["start_time"])
    end = datetime.fromisoformat(case["end_time"])
    checks = {
        "project_scope": run["project_id"] == case["project_id"],
        "status": diagnosis["status"] == case["expected_status"],
        "required_tools": set(case["required_tools"]) <= tool_names,
        "query_scope": all(
            step["input"]["service"] == case["service"]
            and datetime.fromisoformat(step["input"]["start_time"])
            == datetime.fromisoformat(case["start_time"])
            and datetime.fromisoformat(step["input"]["end_time"])
            == datetime.fromisoformat(case["end_time"])
            for step in telemetry_steps
        ),
        "cause_terms": all(
            any(term.casefold() in diagnosis["cause_summary"].casefold() for term in group)
            for group in case["cause_terms"]
        ),
        "required_evidence": set(case["required_evidence"]) <= set(diagnosis["evidence_ids"]),
        "valid_citations": set(diagnosis["evidence_ids"]) <= retrieved_ids,
        "outside_window_excluded": all(
            start <= datetime.fromisoformat(row["timestamp"]) < end
            for step in telemetry_steps
            if step["output"] is not None
            for collection in step["output"].values()
            for row in collection
        ),
        "token_usage_recorded": (
            run["usage"]["input_tokens"] > 0 and run["usage"]["output_tokens"] > 0
        ),
    }
    if case["relevant_chunk_ids"]:
        relevant = set(case["relevant_chunk_ids"])
        chunks = [
            chunk
            for step in tool_steps
            if step["name"] == "search_runbooks" and step["output"] is not None
            for chunk in step["output"]["chunks"]
        ]
        checks["runbook_retrieved"] = bool(relevant & {c["evidence_id"] for c in chunks})
        checks["runbook_cited"] = bool(relevant & set(diagnosis["evidence_ids"]))
        checks["knowledge_project_scope"] = all(
            chunk["project_id"] == case["project_id"] for chunk in chunks
        )
    trajectory = evaluate_trajectory(case, run["steps"])
    checks.update(trajectory["checks"])
    dimensions = {
        "trajectory": all(trajectory["checks"].values()),
        "retrieval": checks.get("runbook_retrieved"),
        "root_cause": checks["status"] and checks["cause_terms"],
        "citations": checks["valid_citations"]
        and checks["required_evidence"]
        and checks.get("runbook_cited", True),
        "task_completion": checks["status"]
        and checks["required_tools"]
        and checks["required_evidence"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "failure_reasons": [name for name, passed in checks.items() if not passed],
        "dimensions": dimensions,
        "trajectory": trajectory,
    }
