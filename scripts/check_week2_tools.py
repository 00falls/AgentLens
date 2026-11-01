"""Validate real MCP transport and scope boundaries without making model requests."""

import asyncio
import json

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from langchain.mcp import MCPAdapter

from agentlens.config import ROOT, Settings
from agentlens.evaluation import load_case


async def main():
    settings = Settings()
    case = load_case("pool-exhaustion-01")
    args = {key: case[key] for key in ["service", "start_time", "end_time"]}
    checks = {}
    for project in ["project-a", "project-b", None]:
        headers = {} if project is None else {"x-agentlens-project": project}
        async with MCPAdapter(
            Client(StreamableHttpTransport(settings.mcp_url, headers=headers), timeout=10)
        ) as adapter:
            tools = {tool.name: tool for tool in await adapter.list_tools()}
            checks["catalog"] = {"search_logs", "query_metrics"} <= set(tools)
            checks["project_not_model_argument"] = all(
                "project_id" not in tool.args_schema["properties"] for tool in tools.values()
            )
            message = await tools["search_logs"].ainvoke(
                {"name": "search_logs", "args": args, "id": "protocol-probe", "type": "tool_call"}
            )
            if project == "project-a":
                assert message.status == "success", message.content
                checks["structured_result"] = (
                    message.artifact["structured_content"]["logs"][0]["evidence_id"]
                    == "pool-exhaustion-log-1"
                )
                invalid = await tools["query_metrics"].ainvoke(
                    {
                        "name": "query_metrics",
                        "id": "bad-window-probe",
                        "type": "tool_call",
                        "args": {**args, "end_time": args["start_time"]},
                    }
                )
                checks["invalid_window_rejected"] = invalid.status == "error"
            elif project == "project-b":
                checks["project_filter"] = message.artifact["structured_content"]["logs"] == []
            else:
                checks["missing_scope_rejected"] = message.status == "error"
    report = {"model_calls": 0, "checks": checks, "passed": all(checks.values())}
    target = ROOT / "reports/week2-mcp-checks.json"
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    assert report["passed"], report


if __name__ == "__main__":
    asyncio.run(main())
