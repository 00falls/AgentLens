import asyncio
import hashlib
import json
from datetime import UTC, datetime
from time import perf_counter

from fastmcp import Client as MCPClient
from fastmcp.client.transports import StreamableHttpTransport
from langchain.mcp import MCPAdapter
from langchain_core.messages import SystemMessage, message_chunk_to_message
from langchain_openai import ChatOpenAI
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import interrupt
from opentelemetry import trace
from opentelemetry.trace import StatusCode

from agentlens.config import ROOT
from agentlens.conversations import archive_experience
from agentlens.db import RunStep
from agentlens.eval_budget import active_budget
from agentlens.finops import gateway_model, price_call
from agentlens.observability import tracer
from agentlens.replay import RecordedTools
from agentlens.schemas import Diagnosis
from agentlens.security import audit, mcp_headers


class InvestigationState(MessagesState):
    model_calls: int
    diagnosis: dict | None
    evidence_ids: list[str]
    telemetry_evidence_ids: list[str]
    experience_context: dict | None
    origin_run_id: str
    experience_approved: bool | None
    experience_id: str | None


class ModelCallLimit(RuntimeError):
    pass


def build_graph(settings, session, run, saver, stack, replay: RecordedTools | None = None):
    prompt_text = (ROOT / "prompts/diagnose.md").read_text(encoding="utf-8")
    sequence = 0
    tools = None

    async def prepare_tools():
        nonlocal tools
        if tools is None:
            if replay is not None:
                tools = replay.catalog
                run.versions = {
                    **run.versions,
                    "tool_catalog": replay.payload["tool_catalog"],
                    "tool_schemas_sha256": replay.payload["source_run"]["versions"][
                        "tool_schemas_sha256"
                    ],
                }
                session.commit()
                return tools
            headers = mcp_headers(settings, run.project_id, run.id)
            if run.scenario_id:
                headers["x-agentlens-scenario"] = run.scenario_id
            transport = StreamableHttpTransport(settings.mcp_url, headers=headers)
            adapter = await stack.enter_async_context(
                MCPAdapter(MCPClient(transport, timeout=settings.request_timeout))
            )
            discovered = await adapter.list_tools()
            tools = {tool.name: tool for tool in discovered}
            schemas = [
                {"name": tool.name, "description": tool.description, "schema": tool.args_schema}
                for tool in discovered
            ]
            run.versions = {
                **run.versions,
                "tool_catalog": schemas,
                "tool_schemas_sha256": hashlib.sha256(
                    json.dumps(schemas, sort_keys=True).encode()
                ).hexdigest(),
            }
            session.commit()
        return tools

    async def record(kind, name, inputs, action):
        nonlocal sequence
        sequence += 1
        step = RunStep(
            run_id=run.id,
            sequence=sequence,
            kind=kind,
            name=name,
            input=inputs,
            output=None,
            error=None,
            duration_ms=0,
        )
        writer = get_stream_writer()
        writer({"event": "step_started", "step": sequence, "kind": kind, "name": name})
        started = perf_counter()
        span = tracer.start_span(
            f"agentlens.{kind}",
            attributes={
                "agentlens.step.sequence": sequence,
                "agentlens.step.kind": kind,
                "agentlens.tool.name" if kind == "tool" else "agentlens.requested_model": name,
            },
        )
        if span.get_span_context().is_valid:
            step.span_id = f"{span.get_span_context().span_id:016x}"
        try:
            with trace.use_span(
                span, end_on_exit=False, record_exception=False, set_status_on_exception=False
            ):
                result, step.output, step.error = await action()
            if replay is not None and kind == "tool":
                step.source_step_sequence = result.artifact["source_step_sequence"]
            if step.error:
                span.set_status(StatusCode.ERROR)
                span.set_attribute("agentlens.tool.error", True)
            elif kind == "model" and step.output["usage"]:
                for key in ["input_tokens", "output_tokens"]:
                    span.set_attribute(f"gen_ai.usage.{key}", step.output["usage"][key])
            elif kind == "tool":
                span.set_attribute(
                    "agentlens.evidence.count", sum(len(rows) for rows in step.output.values())
                )
            return result
        except (Exception, asyncio.CancelledError) as exc:
            span.set_status(StatusCode.ERROR)
            span.set_attribute("error.type", type(exc).__name__)
            step.error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            step.duration_ms = round((perf_counter() - started) * 1000, 2)
            session.add(step)
            session.commit()
            span.end()
            writer(
                {
                    "event": "step_finished",
                    "step": step.sequence,
                    "kind": kind,
                    "name": name,
                    "error": step.error,
                    "duration_ms": step.duration_ms,
                }
            )

    async def decide(state):
        if state["model_calls"] >= settings.max_model_calls:
            raise ModelCallLimit("Agent reached the configured model-call limit")
        catalog = await prepare_tools()
        budget = active_budget.get()
        if budget:
            budget.before_call(
                [SystemMessage(content=prompt_text), *state["messages"]],
                run.versions["tool_catalog"],
                settings.max_output_tokens,
            )
        model = ChatOpenAI(
            model=settings.model,
            base_url=settings.model_base_url,
            api_key=settings.model_api_key,
            timeout=settings.request_timeout,
            max_retries=0,
            max_tokens=settings.max_output_tokens,
            temperature=0,
            stream_usage=True,
            use_responses_api=False,
        ).bind_tools(list(catalog.values()))

        async def call_model():
            combined = None
            writer = get_stream_writer()
            async for chunk in model.astream(
                [SystemMessage(content=prompt_text), *state["messages"]]
            ):
                combined = chunk if combined is None else combined + chunk
                if chunk.content:
                    writer({"event": "answer_delta", "step": sequence, "delta": chunk.content})
            if combined is None:
                raise RuntimeError("Model returned an empty stream")
            message = message_chunk_to_message(combined)
            usage = message.usage_metadata
            if usage is not None:
                run.usage = {
                    "input_tokens": run.usage["input_tokens"] + usage["input_tokens"],
                    "output_tokens": run.usage["output_tokens"] + usage["output_tokens"],
                }
            return (
                message,
                {
                    "content": message.content,
                    "tool_calls": message.tool_calls,
                    "usage": usage,
                    "response_model": message.response_metadata.get("model_name"),
                    "billing": price_call(
                        usage,
                        message.response_metadata.get("model_name"),
                        datetime.now(UTC),
                        gateway_model(settings),
                    ),
                },
                None,
            )

        message = await record(
            "model",
            settings.model,
            {"messages": [m.model_dump(mode="json") for m in state["messages"]]},
            call_model,
        )
        if budget:
            budget.observe(
                price_call(
                    message.usage_metadata,
                    message.response_metadata.get("model_name"),
                    datetime.now(UTC),
                    gateway_model(settings),
                )
            )
        return {"messages": [message], "model_calls": state["model_calls"] + 1}

    async def execute_tools(state):
        catalog = await prepare_tools()
        messages = []
        evidence_ids = set(state["evidence_ids"])
        telemetry_ids = set(state["telemetry_evidence_ids"])
        for call in state["messages"][-1].tool_calls:

            async def execute(call=call):
                message = (
                    await replay.invoke(call)
                    if replay is not None
                    else await catalog[call["name"]].ainvoke({**call, "type": "tool_call"})
                )
                if message.status == "error":
                    return message, None, message.text
                return message, message.artifact["structured_content"], None

            message = await record("tool", call["name"], call["args"], execute)
            if message.status != "error":
                output = message.artifact["structured_content"]
                ids = {row["evidence_id"] for collection in output.values() for row in collection}
                evidence_ids.update(ids)
                if call["name"] in {"search_logs", "query_metrics"}:
                    telemetry_ids.update(ids)
                if call["name"] == "search_runbooks" and output["chunks"]:
                    run.versions = {
                        **run.versions,
                        "retrieval": output["chunks"][0]["retrieval_manifest"],
                    }
                    session.commit()
            messages.append(message)
        return {
            "messages": messages,
            "evidence_ids": sorted(evidence_ids),
            "telemetry_evidence_ids": sorted(telemetry_ids),
        }

    def finalize(state):
        diagnosis = Diagnosis.model_validate_json(state["messages"][-1].content)
        if unknown := set(diagnosis.evidence_ids) - set(state["evidence_ids"]):
            raise ValueError(f"Model cited evidence not retrieved: {sorted(unknown)}")
        if diagnosis.status == "diagnosed" and not (
            set(diagnosis.evidence_ids) & set(state["telemetry_evidence_ids"])
        ):
            raise ValueError("A diagnosed incident requires retrieved telemetry evidence")
        return {"diagnosis": diagnosis.model_dump()}

    def confirm_experience(state):
        approved = interrupt(
            {
                "action": "save_incident_experience",
                "origin_run_id": state["origin_run_id"],
                "context": state["experience_context"],
                "diagnosis": state["diagnosis"],
            }
        )
        return {"experience_approved": approved}

    def archive(state):
        result = archive_experience(session, run.project_id, state)
        audit(
            settings,
            action="experience.confirm",
            resource=result,
            project=run.project_id,
            run_id=run.id,
            detail={"approved": True},
        )
        return {"experience_id": result}

    graph = StateGraph(InvestigationState)
    graph.add_node("decide", decide)
    graph.add_node("tools", execute_tools)
    graph.add_node("finalize", finalize)
    graph.add_node("confirm_experience", confirm_experience)
    graph.add_node("archive", archive)
    graph.add_edge(START, "decide")
    graph.add_conditional_edges(
        "decide", lambda state: "tools" if state["messages"][-1].tool_calls else "finalize"
    )
    graph.add_edge("tools", "decide")
    graph.add_conditional_edges(
        "finalize",
        lambda state: (
            "confirm_experience"
            if state["experience_context"] is not None
            and state["diagnosis"]["status"] == "diagnosed"
            else END
        ),
    )
    graph.add_conditional_edges(
        "confirm_experience", lambda state: "archive" if state["experience_approved"] else END
    )
    graph.add_edge("archive", END)
    return graph.compile(checkpointer=saver)
