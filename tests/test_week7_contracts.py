"""Pure recording/diff contracts; no provider or database requests."""

import asyncio
import copy
import json

import pytest

from agentlens.config import ROOT
from agentlens.evaluation import load_cases
from agentlens.replay import RecordedTools, ReplayMismatch, digest, normalize_arguments
from agentlens.run_diff import compare_runs, locate_failures, write_difference


def log_args(**changes):
    return {
        "service": "order-api",
        "start_time": "2026-10-30T14:00:00+08:00",
        "end_time": "2026-10-30T14:15:00+08:00",
        **changes,
    }


@pytest.fixture
def payload():
    return {
        "tool_catalog": [
            {"name": n, "description": n, "schema": {}}
            for n in ["search_logs", "query_metrics", "search_runbooks"]
        ],
        "calls": [
            {
                "name": "search_logs",
                "arguments": log_args(),
                "output": {"logs": [{"evidence_id": "first", "message": "original"}]},
                "error": None,
                "source_step_sequence": 2,
            },
            {
                "name": "search_logs",
                "arguments": log_args(),
                "output": {"logs": [{"evidence_id": "second"}]},
                "error": None,
                "source_step_sequence": 5,
            },
            {
                "name": "query_metrics",
                "arguments": log_args(),
                "output": None,
                "error": "Recorded database timeout",
                "source_step_sequence": 3,
            },
        ],
    }


def invoke(replay, name="search_logs", args=None):
    return asyncio.run(
        replay.invoke(
            {"id": "candidate-call", "name": name, "args": log_args() if args is None else args}
        )
    )


def test_normalization_fills_defaults_and_unifies_timezones():
    a = normalize_arguments("search_logs", log_args())
    b = normalize_arguments(
        "search_logs",
        log_args(
            level=None,
            limit=50,
            start_time="2026-10-30T06:00:00Z",
            end_time="2026-10-30T06:15:00+00:00",
        ),
    )
    assert a == b
    assert digest({"a": 1, "b": 2}) == digest({"b": 2, "a": 1})


def test_repeated_keys_consume_distinct_results_and_do_not_mutate_recording(payload):
    original = copy.deepcopy(payload)
    replay = RecordedTools(payload)
    one = invoke(replay)
    one.artifact["structured_content"]["logs"][0]["message"] = "candidate mutation"
    two = invoke(replay)
    assert two.artifact["structured_content"]["logs"][0]["evidence_id"] == "second"
    assert two.artifact["source_step_sequence"] == 5
    assert payload == original
    with pytest.raises(ReplayMismatch) as exc:
        invoke(replay)
    assert exc.value.detail["reason"] == "recording_exhausted"
    assert exc.value.detail["occurrence"] == 3


@pytest.mark.parametrize(
    "name,args,reason",
    [
        ("search_logs", log_args(limit=100), "unrecorded_arguments"),
        ("search_logs", log_args(project_id="project-b"), "invalid_arguments"),
        ("search_logs", log_args(end_time="2026-10-30T13:00:00+08:00"), "invalid_arguments"),
        ("search_runbooks", {"query": "new query", "top_k": 3}, "unrecorded_arguments"),
        ("read_secret", {}, "unknown_tool"),
    ],
)
def test_unrecorded_and_invalid_calls_stop(payload, name, args, reason):
    with pytest.raises(ReplayMismatch) as exc:
        invoke(RecordedTools(payload), name, args)
    assert exc.value.detail["code"] == "replay_mismatch"
    assert exc.value.detail["reason"] == reason


def test_recorded_error_remains_an_error_and_independent_keys_can_reorder(payload):
    replay = RecordedTools(payload)
    failed = invoke(replay, "query_metrics")
    assert failed.status == "error"
    assert failed.content == "Recorded database timeout"
    assert failed.artifact["structured_content"] is None
    assert invoke(replay).artifact["source_step_sequence"] == 2


@pytest.fixture
def historical():
    return json.loads((ROOT / "reports/pgvector-acceptance.json").read_text(encoding="utf-8"))[
        "run"
    ]


def test_failure_locations_describe_observations_not_hidden_causes(historical):
    case = load_cases(ROOT / "datasets/week6/dev.jsonl")[0]
    facts = locate_failures(historical, case)
    assert {f["code"] for f in facts} == {
        "labelled_relevant_chunks_not_retrieved",
        "labelled_relevant_chunks_not_cited",
    }
    miss = facts[0]
    assert miss["locations"][0]["step_sequence"] == 4
    assert "causal explanation" in miss["note"]


def test_diff_preserves_full_arguments_answers_and_usage(tmp_path, historical):
    candidate = copy.deepcopy(historical)
    candidate.update(run_id="controlled-candidate", execution_mode="recorded_replay")
    candidate["usage"]["input_tokens"] += 10
    candidate["steps"][1]["input"]["limit"] = 99
    result = compare_runs(historical, candidate)
    assert result["tool_calls"]["added"] and result["tool_calls"]["removed"]
    assert result["usage"]["delta"]["input_tokens"] == 10
    assert result["answers"]["baseline"] == historical["output"]
    assert result["deterministic_reproduction"] is False
    target = tmp_path / "difference.json"
    write_difference(result, target)
    assert target.is_file() and target.with_suffix(".md").is_file()


def test_cross_project_or_changed_question_cannot_be_compared(historical):
    candidate = copy.deepcopy(historical)
    candidate["project_id"] = "project-b"
    with pytest.raises(ValueError, match="same project"):
        compare_runs(historical, candidate)


def test_mismatch_limit_tool_error_and_invalid_citation_have_evidence(historical):
    candidate = copy.deepcopy(historical)
    candidate["failure_detail"] = {"code": "replay_mismatch", "reason": "unrecorded_arguments"}
    candidate["steps"][1]["error"] = "controlled tool failure"
    candidate["output"]["evidence_ids"].append("never-returned")
    facts = locate_failures(candidate)
    assert {"tool_execution_failed", "invalid_citations", "replay_mismatch"} <= {
        f["code"] for f in facts
    }
    candidate["failure_detail"] = {"code": "model_call_limit", "limit": 6}
    assert any(f["code"] == "model_call_limit" for f in locate_failures(candidate))
