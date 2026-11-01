"""A standalone MCP discovery/call probe; not an incident acceptance case."""

import asyncio
import json
from pathlib import Path

import uvicorn
from mcp import Client
from mcp.server import MCPServer

mcp = MCPServer("AgentLens week-one probe")


@mcp.tool()
def echo_service(service: str) -> dict:
    """Echo a service name to verify the MCP protocol and transport."""
    return {"service": service, "probe": True}


async def probe():
    async with Client("http://127.0.0.1:8011/mcp") as client:
        tools = await client.list_tools()
        result = await client.call_tool("echo_service", {"service": "order-api"})
        assert not result.is_error
        report = {
            "tools": [tool.name for tool in tools.tools],
            "result": result.model_dump(mode="json"),
        }
        target = Path(__file__).resolve().parents[1] / "reports/mcp-probe.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(report, ensure_ascii=False, indent=2)
        target.write_text(content + "\n", encoding="utf-8")
        print(content)


if __name__ == "__main__":
    import sys

    if "--serve" in sys.argv:
        uvicorn.run(mcp.streamable_http_app(), host="127.0.0.1", port=8011)
    else:
        asyncio.run(probe())
