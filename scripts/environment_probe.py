"""Collect environment capability facts without printing credentials."""

import json
import platform
import shutil
import subprocess
from importlib.metadata import version

from dotenv import dotenv_values
from sqlalchemy import text

from agentlens.config import ROOT, Settings
from agentlens.db import create_session


def main():
    settings = Settings()
    report = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "dependencies": {
            name: version(name)
            for name in ["langgraph", "langchain-openai", "litellm", "sqlalchemy", "mcp"]
        },
        "deepseek_key_configured": bool(dotenv_values(ROOT / ".env").get("DEEPSEEK_API_KEY")),
        "docker_cli": shutil.which("docker"),
        "openshell_cli": shutil.which("openshell"),
    }
    with create_session(settings) as session:
        report["postgresql"] = session.scalar(text("SELECT version()"))
        report["pgvector_available"] = session.scalar(
            text("SELECT EXISTS(SELECT 1 FROM pg_available_extensions WHERE name='vector')")
        )
        report["telemetry_counts"] = {
            "logs": session.scalar(text("SELECT count(*) FROM log_events")),
            "metrics": session.scalar(text("SELECT count(*) FROM metric_points")),
        }
    if shutil.which("wsl"):
        probe = subprocess.run(["wsl", "--list", "--quiet"], capture_output=True, timeout=15)
        report["wsl_list_exit_code"] = probe.returncode
    target = ROOT / "reports/environment.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
