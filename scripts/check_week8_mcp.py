"""Real MCP HTTP authorization and tool audit, with no provider calls."""

import asyncio
import json

import httpx
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from agentlens.config import ROOT, Settings
from agentlens.security import mcp_headers

SOURCE = "7d81edc0-496d-42ee-a739-77c0d98f2bd1"
QUERY = {
    "service": "order-api",
    "start_time": "2026-10-30T14:00:00+08:00",
    "end_time": "2026-10-30T14:15:00+08:00",
}


async def exercise():
    settings = Settings()
    checks = {}
    async with httpx.AsyncClient(trust_env=False) as http:
        checks["missing_key_denied"] = (await http.post(settings.mcp_url)).status_code == 401
        headers = {**mcp_headers(settings, "project-a"), "x-agentlens-project": "project-b"}
        checks["forged_project_denied"] = (
            await http.post(settings.mcp_url, headers=headers)
        ).status_code == 403
    async with Client(
        StreamableHttpTransport(
            settings.mcp_url, headers=mcp_headers(settings, "project-a", SOURCE)
        )
    ) as client:
        tools = await client.list_tools()
        checks["analysis_tool_discovered"] = "analyze_logs" in {t.name for t in tools}
        result = await client.call_tool("search_logs", QUERY)
        checks["authorized_query_succeeds"] = not result.is_error and bool(result.data["logs"])
        result = await client.call_tool(
            "analyze_logs",
            {"evidence_ids": ["foreign-log"], "python_code": "print('{}')"},
            raise_on_error=False,
        )
        checks["unretrieved_input_denied"] = result.is_error
        result = await client.call_tool(
            "analyze_logs",
            {"evidence_ids": ["pool-exhaustion-log-1"], "python_code": "print('{}')"},
            raise_on_error=False,
        )
        checks["missing_sandbox_explicit_tool_error"] = result.is_error and "OpenShell" in str(
            result.content
        )
    async with Client(
        StreamableHttpTransport(
            settings.mcp_url, headers=mcp_headers(settings, "project-b", SOURCE)
        )
    ) as client:
        result = await client.call_tool("search_logs", QUERY, raise_on_error=False)
        checks["foreign_run_tool_denied"] = result.is_error
    report = {
        "passed": all(checks.values()),
        "provider_requests": 0,
        "checks": checks,
        "sandbox_runtime_executed": False,
    }
    (ROOT / "reports/week8-mcp.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report))
    assert report["passed"]


if __name__ == "__main__":
    asyncio.run(exercise(), loop_factory=asyncio.SelectorEventLoop)
