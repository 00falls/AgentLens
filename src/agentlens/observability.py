"""SDK configuration and run context; business records never depend on export completion."""

import os
from contextlib import contextmanager
from functools import lru_cache

from opentelemetry import baggage, context, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from agentlens.config import Settings

RUN_ATTRIBUTES = ("agentlens.run_id", "agentlens.thread_id", "agentlens.project_id")
tracer = trace.get_tracer("agentlens.business")


class RunAttributesProcessor(SpanProcessor):
    def on_start(self, span, parent_context=None):
        for name in RUN_ATTRIBUTES:
            value = baggage.get_baggage(name, context=parent_context)
            if value is not None:
                span.set_attribute(name, value)


@lru_cache
def configure_tracing(service_name: str):
    # The business database holds visible inputs/results; traces carry only metadata.
    os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "false"
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(RunAttributesProcessor())
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=Settings().otlp_endpoint, timeout=3),
            schedule_delay_millis=500,
        )
    )
    trace.set_tracer_provider(provider)
    HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    OpenAIInstrumentor().instrument(tracer_provider=provider)
    return provider


@contextmanager
def run_span_context(span, run):
    ctx = trace.set_span_in_context(span)
    for name, value in zip(RUN_ATTRIBUTES, (run.id, run.thread_id, run.project_id), strict=True):
        ctx = baggage.set_baggage(name, value, context=ctx)
    token = context.attach(ctx)
    try:
        yield
    finally:
        context.detach(token)
