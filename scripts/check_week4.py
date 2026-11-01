"""Real PG/checkpoints/MCP; replace only external model decisions. No paid business cases."""

import asyncio
import json
import os
import subprocess
import sys
from contextlib import aclosing
from unittest.mock import patch

import httpx
from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage
from sqlalchemy import delete, func, select

from agentlens.agent import investigate, investigation_events, read_run
from agentlens.checkpoints import checkpoints
from agentlens.config import ROOT, Settings
from agentlens.conversations import (
    ConversationError,
    archive_experience,
    create_thread,
    search_experiences,
)
from agentlens.db import KnowledgeDocument, create_session
from agentlens.evaluation import load_case
from agentlens.schemas import ExperienceContext, ExperienceQuery, ResumeRequest

CASE = load_case("pool-exhaustion-01")
PROBE_RUNS = []
CONTEXT = ExperienceContext(
    **{k: CASE[k] for k in ["service", "start_time", "end_time"]},
    applicability="合成连接池饱和场景；不证明慢查询或连接泄漏。",
)
DIAGNOSIS = {
    "status": "diagnosed",
    "cause_summary": "连接池耗尽，等待连接导致请求失败。",
    "evidence_ids": CASE["required_evidence"],
    "unknowns": ["连接占用原因未确认"],
    "next_steps": ["检查慢查询与长事务"],
}


class ScriptedProvider:
    def bind_tools(self, tools):
        return self

    async def astream(self, messages):
        if isinstance(messages[-1], HumanMessage) and "inherit" not in messages[-1].content:
            args = {k: CASE[k] for k in ["service", "start_time", "end_time"]}
            yield AIMessageChunk(
                content="",
                tool_calls=[
                    {"name": name, "args": args, "id": f"contract-{name}"}
                    for name in ["search_logs", "query_metrics"]
                ],
            )
        else:
            assert isinstance(messages[-1], ToolMessage) or "inherit" in messages[-1].content
            yield AIMessageChunk(
                content=json.dumps(DIAGNOSIS, ensure_ascii=False),
                usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            )


class FailingProvider(ScriptedProvider):
    async def astream(self, messages):
        yield AIMessageChunk(content="")
        raise TimeoutError("controlled_provider_timeout")


class WaitingProvider(ScriptedProvider):
    async def astream(self, messages):
        yield AIMessageChunk(content="")
        await asyncio.Event().wait()


async def main():
    settings = Settings()
    checks, probe_runs = {}, PROBE_RUNS
    with create_session(settings) as session:
        thread = create_thread(session, "project-a")["thread_id"]
    with patch("agentlens.graph.ChatOpenAI", return_value=ScriptedProvider()):
        paused = await investigate(
            settings,
            "project-a",
            "Controlled confirmation probe",
            thread_id=thread,
            experience=CONTEXT,
        )
    assert paused["event"] == "run_interrupted", paused
    probe_runs.append(paused["run_id"])
    checks["interrupt_contains_exact_draft"] = paused["interrupt"]["value"][
        "diagnosis"
    ] == DIAGNOSIS and paused["interrupt"]["value"]["context"] == CONTEXT.model_dump(mode="json")
    with create_session(settings) as session:
        rows = search_experiences(session, "project-a", ExperienceQuery(service="order-api"))
        checks["unconfirmed_not_searchable"] = not any(
            r["origin_run_id"] == paused["run_id"] for r in rows["experiences"]
        )
    # A new Python process reconstructs the graph from PostgreSQL, with no provider patch.
    code = """
import asyncio, json, sys
from agentlens.agent import investigate
from agentlens.config import Settings
from agentlens.schemas import ResumeRequest
result=asyncio.run(investigate(Settings(), 'project-a', '', thread_id=sys.argv[1],
    resume=ResumeRequest(checkpoint_id=sys.argv[2], approved=True)),
    loop_factory=asyncio.SelectorEventLoop)
print(json.dumps(result))
"""
    process = subprocess.run(
        [sys.executable, "-c", code, thread, paused["checkpoint_id"]],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1"},
        timeout=30,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    resumed = json.loads(process.stdout)
    checks["fresh_process_resumes_without_model"] = resumed["event"] == "run_finished"
    probe_runs.append(resumed["run_id"])
    async with checkpoints(settings) as saver:
        checkpoint = await saver.aget_tuple({"configurable": {"thread_id": thread}})
    state = checkpoint.checkpoint["channel_values"]
    with create_session(settings) as session:
        archive_experience(session, "project-a", state)
        count = session.scalar(
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(KnowledgeDocument.origin_run_id == paused["run_id"])
        )
        checks["archive_reentry_creates_one_document"] = count == 1
        checks["resume_links_original_run"] = (
            read_run(session, resumed["run_id"])["source_run_id"] == paused["run_id"]
        )
        own = search_experiences(session, "project-a", ExperienceQuery(service="order-api"))
        other = search_experiences(session, "project-b", ExperienceQuery(service="order-api"))
        checks["confirmed_experience_searchable"] = any(
            r["origin_run_id"] == paused["run_id"] for r in own["experiences"]
        )
        checks["other_project_cannot_search_experience"] = other["experiences"] == []
    try:
        await investigate(
            settings,
            "project-a",
            "",
            thread_id=thread,
            resume=ResumeRequest(checkpoint_id=paused["checkpoint_id"], approved=True),
        )
    except ConversationError as exc:
        checks["duplicate_confirmation_conflicts"] = exc.status_code == 409
    with patch("agentlens.graph.ChatOpenAI", return_value=ScriptedProvider()):
        followup = await investigate(
            settings, "project-a", "inherit previous telemetry", thread_id=thread
        )
        rejection = await investigate(
            settings, "project-a", "Controlled rejection probe", experience=CONTEXT
        )
    probe_runs.extend([followup["run_id"], rejection["run_id"]])
    with create_session(settings) as session:
        followup_run = read_run(session, followup["run_id"])
    messages = followup_run["steps"][0]["input"]["messages"]
    checks["followup_inherits_messages_and_citations"] = (
        len(messages) > 1 and followup["diagnosis"]["evidence_ids"] == DIAGNOSIS["evidence_ids"]
    )
    rejected = await investigate(
        settings,
        "project-a",
        "",
        thread_id=rejection["thread_id"],
        resume=ResumeRequest(checkpoint_id=rejection["checkpoint_id"], approved=False),
    )
    probe_runs.append(rejected["run_id"])
    with create_session(settings) as session:
        checks["rejection_finishes_without_archive"] = (
            rejected["event"] == "run_finished"
            and rejected["experience_approved"] is False
            and session.scalar(
                select(KnowledgeDocument.id).where(
                    KnowledgeDocument.origin_run_id == rejection["run_id"]
                )
            )
            is None
        )
    with patch("agentlens.graph.ChatOpenAI", return_value=FailingProvider()):
        failure = [e async for e in investigation_events(settings, "project-a", "Timeout probe")]
    probe_runs.append(failure[-1]["run_id"])
    with create_session(settings) as session:
        failed = read_run(session, failure[-1]["run_id"])
    checks["timeout_is_failed_with_original_error"] = (
        failed["status"] == "failed" and "controlled_provider_timeout" in failed["error"]
    )
    async with checkpoints(settings) as saver:
        failed_checkpoint = await saver.aget_tuple(
            {"configurable": {"thread_id": failed["thread_id"]}}
        )
    with patch("agentlens.graph.ChatOpenAI", return_value=ScriptedProvider()):
        recovered = await investigate(
            settings,
            "project-a",
            "",
            thread_id=failed["thread_id"],
            resume=ResumeRequest(
                checkpoint_id=failed_checkpoint.config["configurable"]["checkpoint_id"]
            ),
        )
    checks["failed_node_explicitly_resumes"] = recovered["event"] == "run_finished"
    probe_runs.append(recovered["run_id"])
    with patch("agentlens.graph.ChatOpenAI", return_value=ScriptedProvider()):
        limited = [
            e
            async for e in investigation_events(
                settings.model_copy(update={"max_model_calls": 1}), "project-a", "Call limit probe"
            )
        ]
    checks["call_budget_exhaustion_is_failure"] = (
        limited[-1]["event"] == "run_failed" and "model-call limit" in limited[-1]["error"]
    )
    probe_runs.append(limited[-1]["run_id"])
    with patch("agentlens.graph.ChatOpenAI", return_value=WaitingProvider()):
        async with aclosing(
            investigation_events(settings, "project-a", "Concurrent run probe")
        ) as s:
            started = await anext(s)
            assert (await anext(s))["event"] == "step_started"
            try:
                await investigate(
                    settings, "project-a", "Overlapping request", thread_id=started["thread_id"]
                )
            except ConversationError as exc:
                checks["same_thread_concurrent_invocation_conflicts"] = exc.status_code == 409
    with create_session(settings) as session:
        checks["closed_stream_is_cancelled"] = read_run(session, started["run_id"])["status"] == (
            "cancelled"
        )
    probe_runs.append(started["run_id"])
    async with checkpoints(settings, started["thread_id"]):
        checks["cancelled_stream_releases_thread_lock"] = True
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=15) as client:
        headers = {"X-AgentLens-Project": "project-b"}
        checks["other_project_thread_api_404"] = (
            client.get(f"/threads/{thread}", headers=headers).status_code == 404
        )
        checks["other_project_run_api_404"] = (
            client.get(f"/runs/{paused['run_id']}", headers=headers).status_code == 404
        )
        checks["other_project_resume_api_404"] = (
            client.post(
                f"/threads/{thread}/resume",
                headers=headers,
                json={"checkpoint_id": paused["checkpoint_id"], "approved": True},
            ).status_code
            == 404
        )
    result = {
        "checks": checks,
        "passed": all(checks.values()),
        "real_postgres": True,
        "real_mcp": True,
        "external_model": "scripted_or_controlled_failure",
        "paid_model_calls": 0,
        "business_quality_result": False,
        "probe_run_ids": probe_runs,
    }
    (ROOT / "reports/week4-contracts.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    assert result["passed"], result


if __name__ == "__main__":
    try:
        asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
    finally:
        # Scripted model conclusions must never remain as searchable business knowledge.
        with create_session(Settings()) as session:
            session.execute(
                delete(KnowledgeDocument).where(
                    KnowledgeDocument.kind == "incident_experience",
                    KnowledgeDocument.origin_run_id.in_(PROBE_RUNS),
                )
            )
            session.commit()
