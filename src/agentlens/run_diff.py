"""Explain recorded facts and labelled checks, without inferring hidden model reasoning."""

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from agentlens.evaluation import evaluate
from agentlens.replay import digest, normalize_arguments


def tool_calls(run: dict) -> list[dict]:
    calls = []
    for step in run["steps"]:
        if step["kind"] != "tool":
            continue
        try:
            normalized = normalize_arguments(step["name"], step["input"])
        except (KeyError, ValidationError):
            normalized = None  # Invalid/unknown attempted calls still belong in the diff.
        calls.append(
            {
                "sequence": step["sequence"],
                "name": step["name"],
                "arguments": step["input"],
                "normalized_arguments": normalized,
                "error": step["error"],
                "source_step_sequence": step.get("source_step_sequence"),
                "key": digest(
                    {
                        "name": step["name"],
                        "arguments": normalized if normalized is not None else step["input"],
                    }
                ),
            }
        )
    return calls


def locate_failures(run: dict, case: dict | None = None) -> list[dict]:
    facts = []
    retrieved = set()
    chunks = []
    for step in run["steps"]:
        if step["kind"] != "tool":
            continue
        location = {
            "run_id": run["run_id"],
            "step_sequence": step["sequence"],
            "field": "error" if step["error"] else "output",
        }
        if step["error"]:
            facts.append(
                {"code": "tool_execution_failed", "observed": step["error"], "location": location}
            )
        if step["output"] is not None:
            retrieved.update(row["evidence_id"] for rows in step["output"].values() for row in rows)
            if step["name"] == "search_runbooks":
                chunks.extend(step["output"]["chunks"])
    if case and case["relevant_chunk_ids"]:
        if not set(case["relevant_chunk_ids"]) & {c["evidence_id"] for c in chunks}:
            facts.append(
                {
                    "code": "labelled_relevant_chunks_not_retrieved",
                    "expected": case["relevant_chunk_ids"],
                    "observed": [c["evidence_id"] for c in chunks],
                    "locations": [
                        {
                            "run_id": run["run_id"],
                            "step_sequence": s["sequence"],
                            "field": "output.chunks",
                        }
                        for s in run["steps"]
                        if s["kind"] == "tool" and s["name"] == "search_runbooks"
                    ],
                    "note": "This identifies a labelled miss, not its causal explanation.",
                }
            )
    if run["output"]:
        invalid = sorted(set(run["output"]["evidence_ids"]) - retrieved)
        if invalid:
            facts.append(
                {
                    "code": "invalid_citations",
                    "observed": invalid,
                    "location": {"run_id": run["run_id"], "field": "output.evidence_ids"},
                }
            )
        if (
            case
            and case["relevant_chunk_ids"]
            and not (set(case["relevant_chunk_ids"]) & set(run["output"]["evidence_ids"]))
        ):
            facts.append(
                {
                    "code": "labelled_relevant_chunks_not_cited",
                    "location": {"run_id": run["run_id"], "field": "output.evidence_ids"},
                }
            )
    detail = run.get("failure_detail")
    if detail:
        facts.append(
            {
                "code": detail["code"],
                "observed": detail,
                "location": {"run_id": run["run_id"], "field": "failure_detail"},
                "locations": [
                    {"run_id": run["run_id"], "step_sequence": s["sequence"], "field": "error"}
                    for s in run["steps"]
                    if s["error"]
                ],
            }
        )
    elif run["error"]:
        facts.append(
            {
                "code": "execution_error",
                "observed": run["error"],
                "location": {"run_id": run["run_id"], "field": "error"},
            }
        )
    return facts


def compare_runs(baseline: dict, candidate: dict, case: dict | None = None) -> dict:
    if baseline["project_id"] != candidate["project_id"] or baseline["input"] != candidate["input"]:
        raise ValueError("Run comparison requires the same project and original input")
    if case and (
        case["project_id"] != baseline["project_id"] or case["input"] != baseline["input"]
    ):
        raise ValueError("Evaluation contract does not match these runs")
    before, after = tool_calls(baseline), tool_calls(candidate)
    a, b = Counter(c["key"] for c in before), Counter(c["key"] for c in after)

    def duration(run):
        return (
            (
                datetime.fromisoformat(run["finished_at"])
                - datetime.fromisoformat(run["started_at"])
            ).total_seconds()
            * 1000
            if run["finished_at"]
            else None
        )

    before_cites = set((baseline["output"] or {}).get("evidence_ids", []))
    after_cites = set((candidate["output"] or {}).get("evidence_ids", []))
    result = {
        "format_version": 1,
        "project_id": baseline["project_id"],
        "baseline_run_id": baseline["run_id"],
        "candidate_run_id": candidate["run_id"],
        "candidate_mode": candidate.get("execution_mode", "live"),
        "model_called": any(s["kind"] == "model" for s in candidate["steps"]),
        "deterministic_reproduction": False,
        "tool_calls": {
            "baseline": before,
            "candidate": after,
            "baseline_counts": dict(Counter(c["name"] for c in before)),
            "candidate_counts": dict(Counter(c["name"] for c in after)),
            "added": [{"key": k, "count": n} for k, n in (b - a).items()],
            "removed": [{"key": k, "count": n} for k, n in (a - b).items()],
        },
        "citations": {
            "added": sorted(after_cites - before_cites),
            "removed": sorted(before_cites - after_cites),
        },
        "answers": {"baseline": baseline["output"], "candidate": candidate["output"]},
        "usage": {
            "baseline": baseline["usage"],
            "candidate": candidate["usage"],
            "delta": {
                k: candidate["usage"][k] - baseline["usage"][k]
                for k in ["input_tokens", "output_tokens"]
            },
        },
        "duration_ms": {"baseline": duration(baseline), "candidate": duration(candidate)},
        "versions": {"baseline": baseline["versions"], "candidate": candidate["versions"]},
        "facts": {
            "baseline": locate_failures(baseline, case),
            "candidate": locate_failures(candidate, case),
        },
        "evaluation": {"baseline": evaluate(case, baseline), "candidate": evaluate(case, candidate)}
        if case
        else None,
    }
    result["duration_ms"]["delta"] = (
        duration(candidate) - duration(baseline)
        if duration(candidate) is not None and duration(baseline) is not None
        else None
    )
    return result


def write_difference(report: dict, target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# 执行差异",
        "",
        f"来源：{report['baseline_run_id']}",
        f"候选：{report['candidate_run_id']}",
        f"模式：{report['candidate_mode']}",
        "",
        "重跑调用模型；不宣称确定性复现。",
        "",
        "| 工具 | 来源次数 | 候选次数 |",
        "|---|---:|---:|",
    ]
    calls = report["tool_calls"]
    for name in sorted(calls["baseline_counts"].keys() | calls["candidate_counts"].keys()):
        lines.append(
            f"| {name} | {calls['baseline_counts'].get(name, 0)} | "
            f"{calls['candidate_counts'].get(name, 0)} |"
        )
    lines += [
        "",
        "## 可观测事实",
        "",
        "```json",
        json.dumps(report["facts"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## 参数、答案与引用",
        "",
        "```json",
        json.dumps(
            {k: report[k] for k in ["tool_calls", "answers", "citations", "usage", "duration_ms"]},
            ensure_ascii=False,
            indent=2,
        ),
        "```",
    ]
    target.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
