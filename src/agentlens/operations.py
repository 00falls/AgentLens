"""Durable metrics use the business ledger; no project/run/trace IDs become metric labels."""

from collections import Counter

from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, HistogramMetricFamily
from sqlalchemy import select

from agentlens.db import Run, RunStep
from agentlens.finops import cost_summary

BUCKETS = [1, 5, 10, 30, 60, 120, float("inf")]
STATUSES = {
    "diagnosed",
    "insufficient_evidence",
    "interrupted",
    "failed",
    "cancelled",
    "replay_mismatch",
}
TOOLS = {"search_logs", "query_metrics", "search_runbooks", "search_experiences", "analyze_logs"}


def ledger(session, project):
    runs = session.scalars(select(Run).where(Run.project_id == project)).all()
    steps = session.scalars(select(RunStep).join(Run).where(Run.project_id == project)).all()
    return runs, steps


def operation_summary(session, project):
    runs, steps = ledger(session, project)
    return {
        "runs": len(runs),
        "statuses": dict(Counter(r.status for r in runs)),
        "tools": dict(Counter(s.name for s in steps if s.kind == "tool")),
        "tool_errors": sum(s.kind == "tool" and bool(s.error) for s in steps),
        "input_tokens": sum(
            (s.output or {}).get("usage", {}).get("input_tokens", 0)
            for s in steps
            if s.kind == "model" and (s.output or {}).get("usage")
        ),
        "output_tokens": sum(
            (s.output or {}).get("usage", {}).get("output_tokens", 0)
            for s in steps
            if s.kind == "model" and (s.output or {}).get("usage")
        ),
        "billing": cost_summary(steps),
        "note": "Includes labeled software probes; costs only from actual model steps.",
    }


class LedgerCollector:
    def __init__(self, runs, steps):
        self.runs, self.steps = runs, steps

    def collect(self):
        finished = [r for r in self.runs if r.finished_at is not None]
        counts = Counter(r.status if r.status in STATUSES else "other" for r in finished)
        metric = CounterMetricFamily(
            "agentlens_runs", "Finished ledger executions", labels=["status"]
        )
        for status in sorted(STATUSES | {"other"}):
            metric.add_metric([status], counts[status])
        yield metric
        duration = [(r.finished_at - r.started_at).total_seconds() for r in finished]
        yield HistogramMetricFamily(
            "agentlens_run_duration_seconds",
            "Finished execution wall time",
            buckets=[
                (str(b) if b != float("inf") else "+Inf", sum(d <= b for d in duration))
                for b in BUCKETS
            ],
            sum_value=sum(duration),
        )
        tools = [s for s in self.steps if s.kind == "tool"]
        metric = CounterMetricFamily(
            "agentlens_tool_calls", "Tool attempts", labels=["tool", "outcome"]
        )
        counts = Counter(
            (s.name if s.name in TOOLS else "other", "error" if s.error else "ok") for s in tools
        )
        for name in sorted(TOOLS | {"other"}):
            for outcome in ("ok", "error"):
                metric.add_metric([name, outcome], counts[name, outcome])
        yield metric
        tokens = CounterMetricFamily(
            "agentlens_model_tokens", "Actual model step tokens", labels=["direction"]
        )
        for direction in ("input", "output"):
            tokens.add_metric(
                [direction],
                sum(
                    (s.output or {}).get("usage", {}).get(f"{direction}_tokens", 0)
                    for s in self.steps
                    if s.kind == "model" and (s.output or {}).get("usage")
                ),
            )
        yield tokens
        billing = cost_summary(self.steps)
        yield CounterMetricFamily(
            "agentlens_model_cost_usd",
            "Known cost subtotal only",
            value=float(billing["known_subtotal"]),
        )
        yield GaugeMetricFamily(
            "agentlens_cost_unknown_calls",
            "Calls without complete pricing",
            value=billing["unknown_calls"],
        )


def prometheus_export(session, project):
    registry = CollectorRegistry()
    registry.register(LedgerCollector(*ledger(session, project)))
    return generate_latest(registry)
