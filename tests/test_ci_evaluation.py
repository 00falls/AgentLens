"""Provider-free checks of frozen selection, quality gating, failure facts and budgets."""

import copy
import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from langchain_core.messages import HumanMessage

from agentlens import eval_budget
from agentlens.ci_evaluation import (
    classify_failures,
    evaluate_ci_gate,
    selected_cases,
    summarize,
)
from agentlens.config import ROOT
from agentlens.eval_budget import BudgetStop, EvaluationBudget


@pytest.fixture
def batches(tmp_path):
    _, cases = selected_cases()
    reference = json.loads((ROOT / "reports/week7-acceptance.json").read_text(encoding="utf-8"))[
        "frozen"
    ]
    report = {
        "schema_version": 2,
        "name": "software contract fixture; no model execution",
        "dataset_sha256": "same-data",
        "evaluator_sha256": "same-evaluator",
        "contract": {"selection": "frozen"},
        "batch_error": None,
        "cases": [
            {
                "case_id": c["case_id"],
                "scenario_group": c["scenario_group"],
                "outcome": "passed",
                "run": copy.deepcopy(reference),
                "evaluation": {"checks": {"status": True}, "dimensions": {}},
                "failure_analysis": {"tags": []},
            }
            for c in cases
        ],
    }
    summarize(report, 10)
    baseline, candidate = tmp_path / "baseline.json", tmp_path / "candidate.json"
    baseline.write_text(json.dumps(report))
    candidate.write_text(json.dumps(report))
    return baseline, candidate, report


def test_selection_is_exactly_ten_development_cases_across_eight_families():
    _, cases = selected_cases()
    assert len(cases) == len({c["case_id"] for c in cases}) == 10
    assert {c["split"] for c in cases} == {"dev"}
    assert len({c["scenario_group"] for c in cases}) == 8


@pytest.mark.parametrize(
    "change",
    [
        "regression",
        "missing",
        "duplicate",
        "execution_error",
        "budget_stop",
        "contract",
        "evaluator",
    ],
)
def test_gate_rejects_bad_candidates(batches, change):
    baseline, candidate, data = batches
    if change == "regression":
        data["cases"][0]["outcome"] = "failed"
        data["cases"][0]["evaluation"]["checks"]["status"] = False
    elif change == "missing":
        data["cases"].pop()
    elif change == "duplicate":
        data["cases"][-1] = copy.deepcopy(data["cases"][0])
    elif change == "execution_error":
        data["cases"][-1]["outcome"] = "execution_error"
        data["cases"][-1]["evaluation"] = None
    elif change == "budget_stop":
        data["batch_error"] = "BudgetStop: no further calls"
    elif change == "contract":
        data["contract"] = {"selection": "different"}
    else:
        data["evaluator_sha256"] = "different-evaluator"
    summarize(data, 10)
    candidate.write_text(json.dumps(data))
    assert not evaluate_ci_gate(baseline, candidate)["passed"]


def test_gate_accepts_same_baseline_with_honest_existing_failure(batches):
    baseline, candidate, data = batches
    data["cases"][-1]["outcome"] = "failed"
    summarize(data, 10)
    baseline.write_text(json.dumps(data))
    candidate.write_text(json.dumps(data))
    assert data["summary"]["pass_rate"] == 0.9
    assert evaluate_ci_gate(baseline, candidate)["passed"]


def test_partial_report_does_not_publish_full_pass_rate(batches):
    _, _, data = batches
    data["cases"] = data["cases"][:3]
    summarize(data, 10)
    assert data["summary"]["pass_rate"] is None
    assert data["summary"]["coverage"] == 0.3
    assert data["summary"]["not_executed"] == 7
    assert data["summary"]["confirmed_passed_of_planned"] == "3/10"


def test_failure_classification_is_evidence_not_hallucination_claim(batches):
    _, cases = selected_cases()
    _, _, data = batches
    run = data["cases"][0]["run"]
    analysis = classify_failures(
        cases[0],
        run,
        {"checks": {"runbook_retrieved": False, "runbook_cited": False, "cause_terms": False}},
    )
    categories = {tag["category"] for tag in analysis["tags"]}
    assert categories == {
        "runbook_not_recalled",
        "citation_missing_or_invalid",
        "root_cause_rules_unmet",
    }
    assert all(tag["locations"] for tag in analysis["tags"])


def test_budget_reserve_and_unknown_usage_stop_future_calls(monkeypatch):
    class Clock:
        @staticmethod
        def now(_):
            return datetime(2026, 11, 1, 6, tzinfo=UTC)

    monkeypatch.setattr(
        eval_budget,
        "datetime",
        type("Time", (), {"now": Clock.now, "fromisoformat": datetime.fromisoformat}),
    )
    budget = EvaluationBudget(Decimal("0.20"))
    budget.before_call([HumanMessage(content="synthetic input")], [], 1200)
    budget.observe({"cost": "0.1999"})
    with pytest.raises(BudgetStop, match="reserve"):
        budget.before_call([HumanMessage(content="synthetic input")], [], 1200)
    with pytest.raises(BudgetStop, match="unknown"):
        budget.observe({"cost": None})
    assert budget.unknown_usage


def test_unknown_pricing_date_prevents_any_provider_call(monkeypatch):
    monkeypatch.setattr(
        eval_budget,
        "datetime",
        type(
            "Time",
            (),
            {
                "now": staticmethod(lambda _: datetime(2027, 1, 1, tzinfo=UTC)),
                "fromisoformat": datetime.fromisoformat,
            },
        ),
    )
    with pytest.raises(BudgetStop, match="verified time window"):
        EvaluationBudget(Decimal(".20")).before_call([HumanMessage(content="x")], [], 1200)
