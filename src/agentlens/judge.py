import hashlib
import json
from importlib.metadata import version
from pathlib import Path
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from agentlens.config import ROOT, Settings


class Criterion(BaseModel):
    score: Literal[0, 1, 2]
    reason: str = Field(min_length=1)
    evidence_ids: list[str]


class Assessment(BaseModel):
    root_cause: Criterion
    citations: Criterion
    task_completion: Criterion
    grounded_actions: Criterion


def judge_input(question: str, run: dict) -> dict:
    payload = {
        "question": question,
        "answer": run["output"],
        "evidence": [
            {"step": step["sequence"], "tool": step["name"], "result": step["output"]}
            for step in run["steps"]
            if step["kind"] == "tool" and step["output"] is not None
        ],
    }
    payload["available_evidence_ids"] = sorted(
        {
            row["evidence_id"]
            for step in payload["evidence"]
            for rows in step["result"].values()
            for row in rows
        }
    )
    return payload


def judge_version(settings: Settings) -> dict:
    return {
        "rubric_sha256": hashlib.sha256((ROOT / "prompts/judge.md").read_bytes()).hexdigest(),
        "judge_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "requested_model": settings.judge_model,
        "configured_upstream_model": settings.configured_upstream_model,
        "temperature": 0,
        "langchain_openai": version("langchain-openai"),
        "human_calibrated": False,
        "role": "advisory",
    }


async def judge_run(settings: Settings, question: str, run: dict) -> dict:
    payload = judge_input(question, run)
    model = ChatOpenAI(
        model=settings.judge_model,
        base_url=settings.model_base_url,
        api_key=settings.model_api_key.get_secret_value(),
        temperature=0,
        max_tokens=1800,
        timeout=settings.request_timeout,
        max_retries=0,
        model_kwargs={"response_format": {"type": "json_object"}},
    )
    response = await model.ainvoke(
        [
            SystemMessage(content=(ROOT / "prompts/judge.md").read_text(encoding="utf-8")),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
        ]
    )
    assessment = Assessment.model_validate_json(response.content)
    available = {
        row["evidence_id"]
        for step in payload["evidence"]
        for rows in step["result"].values()
        for row in rows
    }
    for criterion in assessment.model_dump().values():
        if not set(criterion["evidence_ids"]) <= available:
            raise ValueError("Judge cited evidence absent from the actual tool results")
    return {
        "status": "complete",
        "version": judge_version(settings),
        "scores": assessment.model_dump(),
        "usage": response.usage_metadata,
        "input_sha256": hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
    }
