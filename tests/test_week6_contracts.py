"""Deterministic contracts with recorded components and explicitly controlled mutations."""

import asyncio
import copy
import json
from datetime import datetime

import pytest
from langchain_core.messages import AIMessage

from agentlens.calibration import calibrate, prepare_pack
from agentlens.config import ROOT, Settings
from agentlens.conversations import ConversationError
from agentlens.evaluation import evaluate, load_cases
from agentlens.evaluation_api import list_evaluations, report_path, scoped_comparison, scoped_report
from agentlens.experiments import compare_reports, evaluator_version, run_evaluation
from agentlens.gate import evaluate_gate
from agentlens.judge import judge_input, judge_run
from agentlens.knowledge import corpus


@pytest.fixture
def case():
    return load_cases(ROOT / "datasets/week6/dev.jsonl")[0]


@pytest.fixture
def controlled_run(case):
    # A positive evaluator fixture, not a newly executed or improved business result.
    run = json.loads((ROOT / "reports/pgvector-acceptance.json").read_text(encoding="utf-8"))["run"]
    retrieved = json.loads((ROOT / "reports/pgvector-retrieval.json").read_text(encoding="utf-8"))
    chunks = retrieved["results"]["vector"]["chunks"]
    for step in run["steps"]:
        if step["name"] == "search_runbooks":
            step["output"] = {"chunks": chunks}
    run["output"]["evidence_ids"] = [e for e in run["output"]["evidence_ids"] if "--s" not in e] + [
        "pool-exhaustion--s01"
    ]
    assert evaluate(case, run)["passed"]
    return run


def test_dataset_groups_and_real_fixture_windows():
    dev = load_cases(ROOT / "datasets/week6/dev.jsonl")
    holdout = load_cases(ROOT / "datasets/week6/holdout.jsonl")
    assert (len(dev), len(holdout)) == (40, 20)
    assert not {c["scenario_group"] for c in dev} & {c["scenario_group"] for c in holdout}
    assert len({c["case_id"] for c in dev + holdout}) == 60
    docs, chunks, _ = corpus()
    ownership = {
        c["id"]: next(d["project_id"] for d in docs if d["id"] == c["document_id"]) for c in chunks
    }
    telemetry = json.loads((ROOT / "datasets/week6/telemetry.json").read_text(encoding="utf-8"))
    evidence = telemetry["logs"] + telemetry["metrics"]
    assert not any("expected_cause" in row or "relevant_chunk_ids" in row for row in evidence)
    for c in dev + holdout:
        assert all(ownership[chunk] == c["project_id"] for chunk in c["relevant_chunk_ids"])
        in_window = {
            r["id"]
            for r in evidence
            if r["project_id"] == c["project_id"]
            and r["service"] == c["service"]
            and datetime.fromisoformat(c["start_time"])
            <= datetime.fromisoformat(r["timestamp"])
            < datetime.fromisoformat(c["end_time"])
        }
        assert set(c["required_evidence"]) <= in_window


@pytest.mark.parametrize(
    "mutation,failed_check",
    [
        ("invented_citation", "valid_citations"),
        ("wrong_scope", "trajectory_parameters"),
        ("forbidden_tool", "trajectory_forbidden_tools"),
        ("missing_tool", "trajectory_required_tools"),
        ("wrong_order", "trajectory_order"),
        ("unrelated_retrieval", "runbook_retrieved"),
    ],
)
def test_detects_controlled_regressions(case, controlled_run, mutation, failed_check):
    run = copy.deepcopy(controlled_run)
    if mutation == "invented_citation":
        run["output"]["evidence_ids"].append("never-returned-id")
    elif mutation == "wrong_scope":
        next(s for s in run["steps"] if s["name"] == "search_logs")["input"]["service"] = (
            "other-api"
        )
    elif mutation == "forbidden_tool":
        run["steps"].append({"kind": "tool", "name": "read_secret", "input": {}, "output": None})
    elif mutation == "missing_tool":
        run["steps"] = [s for s in run["steps"] if s["name"] != "query_metrics"]
    elif mutation == "wrong_order":
        run["steps"].sort(key=lambda s: s["name"] != "search_runbooks")
    elif mutation == "unrelated_retrieval":
        for step in run["steps"]:
            if step["name"] == "search_runbooks":
                step["output"] = {"chunks": []}
    verdict = evaluate(case, run)
    assert not verdict["passed"]
    assert verdict["checks"][failed_check] is False


def test_telemetry_order_is_flexible_but_retrieval_requires_evidence(case, controlled_run):
    tools = [s for s in controlled_run["steps"] if s["kind"] == "tool"]
    telemetry = [s for s in tools if s["name"] in {"search_logs", "query_metrics"}]
    rest = [s for s in tools if s not in telemetry]
    controlled_run["steps"] = list(reversed(telemetry)) + rest
    assert evaluate(case, controlled_run)["passed"]


def test_unfinished_run_has_explainable_failure(case, controlled_run):
    controlled_run["output"] = None
    verdict = evaluate(case, controlled_run)
    assert verdict["failure_reasons"] == ["run_completed"]


@pytest.fixture
def report_pair(tmp_path, controlled_run):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps({"run": controlled_run}), encoding="utf-8")
    directory = tmp_path / "experiments"
    before, after = directory / "before.json", directory / "after.json"
    for path in [before, after]:
        asyncio.run(
            run_evaluation(
                Settings(),
                ROOT / "datasets/week6/dev.jsonl",
                ["pool-exhaustion-01"],
                path.stem,
                path,
                recorded_file=snapshot,
            )
        )
    return before, after


def test_gate_rejects_regression_and_accepts_restored_snapshot(tmp_path, report_pair):
    before, after = report_pair
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps({"required_case_ids": ["pool-exhaustion-01"], "require_judge": False}),
        encoding="utf-8",
    )
    good = after.read_bytes()
    report = json.loads(good)
    case = load_cases(ROOT / "datasets/week6/dev.jsonl")[0]
    row = report["cases"][0]
    row["run"]["output"]["evidence_ids"].append("invented-id")
    row["evaluation"] = evaluate(case, row["run"])
    row["outcome"] = "failed"
    report["summary"].update(passed=0, failed=1, pass_rate=0)
    after.write_text(json.dumps(report), encoding="utf-8")
    assert not evaluate_gate(before, after, policy)["passed"]
    after.write_bytes(good)
    assert evaluate_gate(before, after, policy)["passed"]
    policy.write_text(
        json.dumps({"required_case_ids": ["pool-exhaustion-01"], "require_judge": True}),
        encoding="utf-8",
    )
    assert evaluate_gate(before, after, policy)["failures"][0]["reason"] == "judge_missing_or_error"


def test_comparison_rejects_contract_drift(report_pair):
    before, after = report_pair
    r = json.loads(after.read_text(encoding="utf-8"))
    r["evaluator_sha256"] = "different-evaluator"
    after.write_text(json.dumps(r))
    with pytest.raises(ValueError, match="evaluator_sha256"):
        compare_reports(before, after)


def test_project_scoped_artifacts_and_traversal(report_pair):
    before, after = report_pair
    assert scoped_report(before, "project-a")["summary"]["selected"] == 1
    assert list_evaluations(before.parent, "project-b") == []
    with pytest.raises(ConversationError) as exc:
        scoped_report(before, "project-b")
    assert exc.value.status_code == 404
    with pytest.raises(ConversationError) as exc:
        report_path(before.parent, "../before")
    assert exc.value.status_code == 422
    rows = scoped_comparison(before.parent, before.stem, after.stem, "project-a")["cases"]
    assert len(rows) == 1


def test_judge_uses_actual_evidence_and_rejects_fabricated_ids(monkeypatch, controlled_run):
    import agentlens.judge as module

    payload = judge_input(controlled_run["input"], controlled_run)
    assert set(payload) == {"question", "answer", "evidence", "available_evidence_ids"}
    assert "expected_cause" not in json.dumps(payload)
    result = {
        name: {"score": 2, "reason": "protocol fixture", "evidence_ids": ["invented-id"]}
        for name in ["root_cause", "citations", "task_completion", "grounded_actions"]
    }

    class ExternalModel:
        def __init__(self, **kwargs):
            pass

        async def ainvoke(self, messages):
            return AIMessage(content=json.dumps(result))

    monkeypatch.setattr(module, "ChatOpenAI", ExternalModel)
    with pytest.raises(ValueError, match="absent"):
        asyncio.run(judge_run(Settings(), controlled_run["input"], controlled_run))


def test_calibration_requires_explicit_label_origin(tmp_path, report_pair):
    source, _ = report_pair
    pack_path = tmp_path / "labels.json"
    prepare_pack(source, pack_path)
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    assert len(pack["samples"]) == 12
    assert all(s["reference"] is None for s in pack["samples"])
    with pytest.raises(ValueError, match="origin"):
        asyncio.run(calibrate(Settings(), pack_path, tmp_path / "calibration.json"))


def test_manifest_records_real_evaluator_version():
    assert len(evaluator_version()) == 64
