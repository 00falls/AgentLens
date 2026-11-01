"""Exercise the real LangChain/OpenAI streaming stack with a controlled HTTP response."""

import asyncio
import json
from unittest.mock import patch

import httpx
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agentlens.config import ROOT
from agentlens.observability import configure_tracing, tracer


async def check():
    canary = "not-a-real-key-sdk-canary"
    prompt = "not-a-real-prompt-sdk-canary"
    chunks = [
        {
            "id": "controlled-sdk",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "controlled-sdk-model",
            "choices": [
                {"index": 0, "delta": {"role": "assistant", "content": "ok"}, "finish_reason": None}
            ],
        },
        {
            "id": "controlled-sdk",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "controlled-sdk-model",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        },
        {
            "id": "controlled-sdk",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "controlled-sdk-model",
            "choices": [],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
        },
    ]
    data = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"

    async def respond(request):
        assert request.headers["authorization"] == f"Bearer {canary}"
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=data)

    exporter = InMemorySpanExporter()
    with patch("agentlens.observability.OTLPSpanExporter", return_value=exporter):
        provider = configure_tracing("agentlens-sdk-contract")
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        model = ChatOpenAI(
            model="controlled-sdk-model",
            base_url="http://controlled.invalid/v1",
            api_key=canary,
            http_async_client=client,
            stream_usage=True,
            max_retries=0,
            use_responses_api=False,
        )
        combined = None
        with tracer.start_as_current_span("controlled.sdk.streaming"):
            async for chunk in model.astream([HumanMessage(content=prompt)]):
                combined = chunk if combined is None else combined + chunk
    provider.force_flush()
    spans = [
        s
        for s in exporter.get_finished_spans()
        if s.instrumentation_scope.name == "opentelemetry.instrumentation.openai_v2"
    ]
    serialized = json.dumps(
        [
            {
                "attributes": dict(s.attributes),
                "events": [{"name": e.name, "attributes": dict(e.attributes)} for e in s.events],
            }
            for s in spans
        ]
    )
    checks = {
        "real_langchain_stream_consumed": combined.content == "ok",
        "stream_usage_preserved": combined.usage_metadata["input_tokens"] == 2
        and combined.usage_metadata["output_tokens"] == 1,
        "official_openai_auto_span_created": bool(spans),
        "prompt_and_key_absent_in_sdk_span": prompt not in serialized and canary not in serialized,
    }
    report = {
        "passed": all(checks.values()),
        "checks": checks,
        "provider_requests": 0,
        "transport": "httpx.MockTransport",
        "auto_span_count": len(spans),
    }
    (ROOT / "reports/week5-sdk-checks.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    provider.shutdown()
    print(json.dumps(report, indent=2))
    assert report["passed"]


if __name__ == "__main__":
    asyncio.run(check(), loop_factory=asyncio.SelectorEventLoop)
