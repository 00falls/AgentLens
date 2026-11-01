"""Measure fixed HTTP/API and MCP tools separately from real model end-to-end latency."""

import asyncio
import json
import os
import platform
from concurrent.futures import ThreadPoolExecutor
from statistics import median
from time import perf_counter

import httpx
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from sqlalchemy import text

from agentlens.config import ROOT, Settings
from agentlens.db import create_session
from agentlens.security import mcp_headers

QUERY = {
    "service": "order-api",
    "start_time": "2026-10-30T14:00:00+08:00",
    "end_time": "2026-10-30T14:15:00+08:00",
    "limit": 100,
}


def summarize(times, elapsed, concurrency):
    ordered = sorted(times)
    return {
        "requests": len(times),
        "concurrency": concurrency,
        "elapsed_seconds": round(elapsed, 4),
        "requests_per_second": round(len(times) / elapsed, 2),
        "p50_ms": round(median(times) * 1000, 3),
        "p95_ms": round(ordered[int((len(times) - 1) * 0.95)] * 1000, 3),
        "errors": 0,
    }


async def mcp_benchmark(settings):
    times = []

    async def worker():
        async with Client(
            StreamableHttpTransport(settings.mcp_url, headers=mcp_headers(settings, "project-a"))
        ) as client:
            await client.call_tool("search_logs", QUERY)
            for _ in range(12):
                start = perf_counter()
                result = await client.call_tool("search_logs", QUERY)
                if result.is_error:
                    raise RuntimeError("Benchmark tool failed")
                times.append(perf_counter() - start)

    start = perf_counter()
    await asyncio.gather(*(worker() for _ in range(4)))
    return summarize(times, perf_counter() - start, 4)


def main():
    settings = Settings()
    with httpx.Client(
        trust_env=False, timeout=20, headers=mcp_headers(settings, "project-a")
    ) as client:
        for _ in range(4):
            client.get("http://127.0.0.1:8000/runs?limit=8").raise_for_status()

        def call(_):
            start = perf_counter()
            client.get("http://127.0.0.1:8000/runs?limit=8").raise_for_status()
            return perf_counter() - start

        start = perf_counter()
        with ThreadPoolExecutor(max_workers=4) as pool:
            times = list(pool.map(call, range(48)))
        api = summarize(times, perf_counter() - start, 4)
    tool = asyncio.run(mcp_benchmark(settings), loop_factory=asyncio.SelectorEventLoop)
    with create_session(settings) as session:
        counts = {
            table: session.execute(text(f"SELECT count(*) FROM {table}")).scalar()
            for table in ("runs", "run_steps", "log_events", "metric_points", "knowledge_chunks")
        }
        plan = session.execute(
            text(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                "SELECT * FROM log_events WHERE project_id='project-a' AND service='order-api' "
                "AND timestamp >= '2026-10-30T06:00:00Z' AND timestamp < '2026-10-30T06:15:00Z' "
                "ORDER BY timestamp,id LIMIT 100"
            )
        ).scalar()
    report = {
        "synthetic_data": True,
        "provider_requests": 0,
        "hardware": {
            "os": platform.platform(),
            "processor": platform.processor(),
            "logical_cpus": os.cpu_count(),
        },
        "row_counts": counts,
        "api_list_runs": api,
        "mcp_search_logs": tool,
        "query_plan": plan,
        "note": "Includes HTTP/auth/audit. MCP elapsed includes setup and 4 warmups; "
        "latency percentiles exclude warmups. No model latency is mixed in.",
    }
    (ROOT / "reports/week9-performance.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"api": api, "mcp": tool}))


if __name__ == "__main__":
    main()
