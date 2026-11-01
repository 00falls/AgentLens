"""AgentEvals matches tool names/arguments; business precedence stays explicit."""

import json
from datetime import datetime

from agentevals.trajectory.match import create_trajectory_match_evaluator


def canonical_args(args: dict) -> dict:
    return {
        k: datetime.fromisoformat(v).isoformat() if k in {"start_time", "end_time"} else v
        for k, v in args.items()
    }


def messages(calls: list[tuple[str, dict]]) -> list[dict]:
    return [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": str(i),
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(canonical_args(args))},
                }
            ],
        }
        for i, (name, args) in enumerate(calls)
    ]


def evaluate_trajectory(case: dict, steps: list[dict]) -> dict:
    calls = [(step["name"], step["input"]) for step in steps if step["kind"] == "tool"]
    names = [name for name, _ in calls]
    name_match = create_trajectory_match_evaluator(
        trajectory_match_mode="superset", tool_args_match_mode="ignore"
    )(
        outputs=messages(calls),
        reference_outputs=messages([(name, {}) for name in case["required_tools"]]),
    )
    parameters = case["tool_parameters"]
    constrained = [(name, args) for name, args in calls if name in parameters]
    argument_match = create_trajectory_match_evaluator(
        trajectory_match_mode="unordered",
        tool_args_match_mode="ignore",
        tool_args_match_overrides={name: list(args) for name, args in parameters.items()},
    )(
        outputs=messages(constrained),
        reference_outputs=messages([(name, parameters[name]) for name, _ in constrained]),
    )
    precedence = {
        f"{a} -> {b}": a in names and b in names and names.index(a) < names.index(b)
        for a, b in case["tool_order"]
    }
    return {
        "checks": {
            "trajectory_required_tools": bool(name_match["score"]),
            "trajectory_forbidden_tools": not bool(set(names) & set(case["forbidden_tools"])),
            "trajectory_parameters": bool(argument_match["score"]),
            "trajectory_order": all(precedence.values()),
        },
        "matcher": "agentevals.trajectory.match",
        "required_tool_match": name_match,
        "parameter_match": argument_match,
        "precedence": precedence,
    }
