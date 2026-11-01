"""Actual PG/checkpoints/MCP metadata; only the external decision model is scripted."""

import asyncio
import json

import pytest
from langchain_core.messages import AIMessageChunk
from sqlalchemy import select, text

from agentlens.agent import investigation_events, read_run
from agentlens.config import ROOT, Settings
from agentlens.conversations import ConversationError
from agentlens.db import Recording, create_session
from agentlens.frozen import freeze_scenario, read_scenario, tool_session, verify_scenario
from agentlens.recordings import capture_recording, read_recording
from agentlens.schemas import LogQuery, ResumeRequest
from agentlens.tools import search_logs

SOURCE = "302c48a7-9420-4b60-9ee6-477f6da3e6f0"


def run(coro):
    return asyncio.run(coro, loop_factory=asyncio.SelectorEventLoop)


@pytest.fixture(scope="module")
def artifacts():
    settings = Settings()
    with create_session(settings) as session:
        previous = session.scalar(select(Recording).where(Recording.source_run_id == SOURCE))
        recording = read_recording(session, previous.id, "project-a") if previous else None
    if recording is None:
        recording = run(capture_recording(settings, SOURCE, "project-a"))
    scenario = freeze_scenario(settings, "pool-exhaustion-01", "project-a", SOURCE)
    yield settings, recording, scenario


def test_actual_vector_snapshot_isolated_and_integrity_checked(artifacts):
    settings, _, scenario = artifacts
    verify_scenario(settings, scenario)
    with create_session(settings) as session:
        message = session.scalar(
            text("SELECT message FROM log_events WHERE id='pool-exhaustion-log-1'")
        )
    try:
        with create_session(settings) as session:
            session.execute(
                text(
                    "UPDATE log_events SET message='controlled live change' "
                    "WHERE id='pool-exhaustion-log-1'"
                )
            )
            session.commit()
        with tool_session(settings, "project-a", scenario["scenario_id"]) as session:
            query = LogQuery(
                service="order-api",
                start_time="2026-10-30T14:00:00+08:00",
                end_time="2026-10-30T14:15:00+08:00",
            )
            assert search_logs(session, "project-a", query)["logs"][0]["message"] == message
            assert (
                session.scalar(
                    text(
                        f"SELECT vector_dims(embedding) FROM "
                        f"{scenario['schema_name']}.knowledge_chunks LIMIT 1"
                    )
                )
                == 512
            )
        verify_scenario(settings, scenario)
    finally:
        with create_session(settings) as session:
            session.execute(
                text("UPDATE log_events SET message=:message WHERE id='pool-exhaustion-log-1'"),
                {"message": message},
            )
            session.commit()
    schema = scenario["schema_name"]
    try:
        with create_session(settings) as session:
            session.execute(
                text(
                    f"UPDATE {schema}.log_events SET message='controlled tamper' "
                    "WHERE id='pool-exhaustion-log-1'"
                )
            )
            session.commit()
        with pytest.raises(ConversationError, match="data changed"):
            verify_scenario(settings, scenario)
    finally:
        with create_session(settings) as session:
            session.execute(
                text(
                    f"UPDATE {schema}.log_events SET message=:message "
                    "WHERE id='pool-exhaustion-log-1'"
                ),
                {"message": message},
            )
            session.commit()


def test_registry_scope_and_no_unknown_scenario_fallback(artifacts):
    settings, recording, scenario = artifacts
    with create_session(settings) as session:
        for read, id_ in [
            (read_recording, recording["recording_id"]),
            (read_scenario, scenario["scenario_id"]),
        ]:
            with pytest.raises(ConversationError) as error:
                read(session, id_, "project-b")
            assert error.value.status_code == 404
    with pytest.raises(ConversationError):
        tool_session(settings, "project-a", "not-a-scenario")


def test_recording_tamper_rejected(artifacts):
    settings, recording, _ = artifacts
    from agentlens.db import Recording

    with create_session(settings) as session:
        row = session.get(Recording, recording["recording_id"])
        original = row.sha256
        try:
            row.sha256 = "0" * 64
            session.commit()
            with pytest.raises(ConversationError, match="integrity"):
                read_recording(session, row.id, "project-a")
        finally:
            row.sha256 = original
            session.commit()


def test_real_graph_replay_without_mcp_and_replay_resume_rejected(monkeypatch, artifacts):
    import agentlens.graph as module

    settings, recording, _ = artifacts
    steps = recording["payload"]["calls"]
    source = recording["payload"]["source_run"]
    calls = [
        {"name": s["name"], "args": s["arguments"], "id": str(i), "type": "tool_call"}
        for i, s in enumerate(steps)
    ]

    class ScriptedModel:
        def __init__(self, **kwargs):
            pass

        def bind_tools(self, tools):
            return self

        async def astream(self, messages):
            if messages[-1].type == "human":
                yield AIMessageChunk(content="", tool_calls=calls)
            else:
                yield AIMessageChunk(content=json.dumps(source["output"], ensure_ascii=False))

    class NoMCP:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Replay must not discover or call MCP")

    monkeypatch.setattr(module, "ChatOpenAI", ScriptedModel)
    monkeypatch.setattr(module, "MCPAdapter", NoMCP)
    settings = settings.model_copy(
        update={
            "model": "Controlled replay protocol probe",
            "configured_upstream_model": "controlled/no-provider",
            "mcp_url": "http://127.0.0.1:1/unreachable",
        }
    )

    async def collect():
        return [
            e
            async for e in investigation_events(
                settings, "project-a", source["input"], recording=recording
            )
        ]

    events = run(collect())
    assert events[-1]["event"] == "run_finished", events[-1]
    with create_session(settings) as session:
        result = read_run(session, events[-1]["run_id"])
    assert result["usage"] == {"input_tokens": 0, "output_tokens": 0}
    assert [s["source_step_sequence"] for s in result["steps"] if s["kind"] == "tool"] == [
        s["source_step_sequence"] for s in steps
    ]
    assert result["source_run_id"] == SOURCE
    assert result["execution_mode"] == "recorded_replay"
    with pytest.raises(ConversationError, match="original recording"):
        run(capture_recording(settings, result["run_id"], "project-a"))

    async def resume():
        return [
            e
            async for e in investigation_events(
                settings,
                "project-a",
                "",
                thread_id=result["thread_id"],
                resume=ResumeRequest(checkpoint_id=result["checkpoint_id"]),
            )
        ]

    with pytest.raises(ConversationError, match="cannot be resumed"):
        run(resume())
    target = ROOT / "reports/week7-components.json"
    target.write_text(
        json.dumps(
            {
                "passed": True,
                "provider_requests": 0,
                "recording_id": recording["recording_id"],
                "scenario_id": artifacts[2]["scenario_id"],
                "controlled_run_id": result["run_id"],
                "checks": [
                    "real_pgvector_snapshot",
                    "live_data_isolation",
                    "snapshot_tamper_rejected",
                    "registry_project_scope",
                    "unknown_scenario_no_fallback",
                    "recording_tamper_rejected",
                    "real_graph_no_mcp",
                    "source_step_links",
                    "isolated_resume_blocked",
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
