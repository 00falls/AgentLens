"""Recorded tool dispatch never opens an MCP connection or queries business data."""

import copy
import hashlib
import json
from collections import defaultdict
from datetime import UTC

from langchain_core.messages import ToolMessage
from pydantic import ValidationError

from agentlens.schemas import AnalysisQuery, ExperienceQuery, LogQuery, MetricQuery, RunbookQuery

CONTRACTS = {
    "analyze_logs": AnalysisQuery,
    "search_logs": LogQuery,
    "query_metrics": MetricQuery,
    "search_runbooks": RunbookQuery,
    "search_experiences": ExperienceQuery,
}


def digest(value: dict | list) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def normalize_arguments(name: str, arguments: dict) -> dict:
    validated = CONTRACTS[name].model_validate(arguments, extra="forbid")
    result = validated.model_dump(mode="json")
    for key in ["start_time", "end_time"]:
        if key in result:
            result[key] = getattr(validated, key).astimezone(UTC).isoformat()
    return result


class ReplayMismatch(RuntimeError):
    def __init__(self, detail: dict):
        self.detail = {"code": "replay_mismatch", **detail}
        super().__init__(json.dumps(self.detail, ensure_ascii=False))


class RecordedTools:
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = defaultdict(list)
        self.used = defaultdict(int)
        for call in payload["calls"]:
            self.calls[self.key(call["name"], call["arguments"])].append(call)

    @staticmethod
    def key(name: str, arguments: dict) -> str:
        return digest({"name": name, "arguments": normalize_arguments(name, arguments)})

    @property
    def catalog(self) -> dict:
        return {
            t["name"]: {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["schema"],
                },
            }
            for t in self.payload["tool_catalog"]
        }

    async def invoke(self, call: dict) -> ToolMessage:
        name, arguments = call["name"], call["args"]
        if name not in CONTRACTS or name not in self.catalog:
            raise ReplayMismatch(
                {"reason": "unknown_tool", "tool": name, "requested_arguments": arguments}
            )
        try:
            key = self.key(name, arguments)
        except ValidationError as exc:
            raise ReplayMismatch(
                {
                    "reason": "invalid_arguments",
                    "tool": name,
                    "requested_arguments": arguments,
                    "validation": exc.errors(include_url=False, include_context=False),
                }
            ) from exc
        occurrence = self.used[key]
        matches = self.calls.get(key, [])
        if occurrence >= len(matches):
            raise ReplayMismatch(
                {
                    "reason": "recording_exhausted" if matches else "unrecorded_arguments",
                    "tool": name,
                    "requested_arguments": arguments,
                    "normalized_arguments": normalize_arguments(name, arguments),
                    "occurrence": occurrence + 1,
                    "recorded_candidates": [
                        {
                            "source_step_sequence": c["source_step_sequence"],
                            "arguments": c["arguments"],
                        }
                        for c in self.payload["calls"]
                        if c["name"] == name
                    ],
                }
            )
        recorded = matches[occurrence]
        self.used[key] += 1
        output = copy.deepcopy(recorded["output"])
        return ToolMessage(
            name=name,
            tool_call_id=call["id"],
            status="error" if recorded["error"] is not None else "success",
            content=recorded["error"]
            if recorded["error"] is not None
            else json.dumps(output, ensure_ascii=False),
            artifact={
                "structured_content": output,
                "source_step_sequence": recorded["source_step_sequence"],
            },
        )
