import hashlib
import json
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from uuid import uuid4

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from langchain.mcp import MCPAdapter
from sqlalchemy import select

from agentlens.agent import read_run
from agentlens.config import ROOT, Settings
from agentlens.conversations import ConversationError
from agentlens.db import Recording, create_session
from agentlens.evaluation import load_cases
from agentlens.replay import digest, normalize_arguments
from agentlens.security import mcp_headers


def read_recording(session, recording_id: str, project: str) -> dict:
    row = session.scalar(
        select(Recording).where(Recording.id == recording_id, Recording.project_id == project)
    )
    if row is None:
        raise ConversationError(404, "Recording not found")
    if digest(row.payload) != row.sha256:
        raise ConversationError(409, "Recording integrity check failed")
    return {
        "recording_id": row.id,
        "source_run_id": row.source_run_id,
        "project_id": row.project_id,
        "sha256": row.sha256,
        "created_at": row.created_at.isoformat(),
        "payload": row.payload,
    }


async def capture_recording(settings: Settings, source_id: str, project: str) -> dict:
    with create_session(settings) as session:
        source = read_run(session, source_id, project)
        if source is None:
            raise ConversationError(404, "Run not found")
        if source["execution_mode"] == "recorded_replay":
            raise ConversationError(
                409,
                "Reuse the original recording; replay attempts are "
                "not a new source of tool observations",
            )
        if source["status"] in {"running", "interrupted", "cancelled"}:
            raise ConversationError(409, "Record a finished, standalone invocation")
        model_steps = [s for s in source["steps"] if s["kind"] == "model"]
        if not model_steps or len(model_steps[0]["input"]["messages"]) != 1:
            raise ConversationError(409, "Replay v1 supports a single initial user turn only")
        first = model_steps[0]["input"]["messages"][0]
        if first["type"] != "human" or first["content"] != source["input"]:
            raise ConversationError(409, "Source input does not describe the initial model context")
        catalog = source["versions"].get("tool_catalog")
        provenance = "captured_with_source_run"
        if catalog is None:
            # Early runs stored only the hash. Recover metadata only if it exactly matches;
            # this export step lists tools but never executes a business tool.
            async with AsyncExitStack() as stack:
                adapter = await stack.enter_async_context(
                    MCPAdapter(
                        Client(
                            StreamableHttpTransport(
                                settings.mcp_url, headers=mcp_headers(settings, project)
                            ),
                            timeout=settings.request_timeout,
                        )
                    )
                )
                tools = await adapter.list_tools()
                catalog = [
                    {"name": t.name, "description": t.description, "schema": t.args_schema}
                    for t in tools
                ]
            actual = hashlib.sha256(json.dumps(catalog, sort_keys=True).encode()).hexdigest()
            if actual != source["versions"].get("tool_schemas_sha256"):
                raise ConversationError(
                    409,
                    "Current tool catalog differs from source; cannot "
                    "reconstruct an unrecorded historical contract",
                )
            provenance = "current_metadata_verified_against_source_hash"
        calls = []
        for step in source["steps"]:
            if step["kind"] == "tool":
                normalize_arguments(step["name"], step["input"])
                if step["output"] is None and step["error"] is None:
                    raise ConversationError(409, "Source contains an unfinished tool step")
                calls.append(
                    {
                        "name": step["name"],
                        "arguments": step["input"],
                        "output": step["output"],
                        "error": step["error"],
                        "source_step_sequence": step["sequence"],
                    }
                )
        cases = load_cases(ROOT / "datasets/week6/dev.jsonl")
        case = next(
            (c for c in cases if c["project_id"] == project and c["input"] == source["input"]), None
        )
        payload = {
            "format_version": 1,
            "source_run": source,
            "calls": calls,
            "tool_catalog": catalog,
            "catalog_provenance": provenance,
            "case": case,
            "matching": "tool + validated defaulted args + per-key occurrence",
            "normalization_version": "pydantic-defaults-utc-v1",
        }
        row = Recording(
            id=str(uuid4()),
            project_id=project,
            source_run_id=source_id,
            payload=payload,
            sha256=digest(payload),
            created_at=datetime.now(UTC),
        )
        session.add(row)
        session.commit()
        return read_recording(session, row.id, project)


def list_recordings(session, project: str) -> list[dict]:
    return [
        {
            "recording_id": r.id,
            "source_run_id": r.source_run_id,
            "created_at": r.created_at.isoformat(),
            "sha256": r.sha256,
            "tool_calls": len(r.payload["calls"]),
            "case_id": r.payload["case"]["case_id"] if r.payload["case"] else None,
        }
        for r in session.scalars(
            select(Recording)
            .where(Recording.project_id == project)
            .order_by(Recording.created_at.desc())
        )
    ]
