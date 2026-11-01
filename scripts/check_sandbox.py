"""Actual OpenShell probes; never substitute local Python for unavailable isolation."""

import json

from agentlens.config import ROOT, Settings
from agentlens.sandbox import SandboxExecutionError, SandboxUnavailable, execute_analysis


def main():
    settings = Settings()
    checks = {}
    tasks = {
        "authorized_statistics": "print(json.dumps({'count': len(logs)}))",
        "forbidden_file": "print(open('/opt/agentlens/denied.txt').read())",
        "forbidden_network": "import socket; socket.create_connection(('1.1.1.1',443),2)",
        "wall_timeout": "import time; time.sleep(30)",
        "memory_limit": "x=bytearray(1024**3)",
        "output_limit": "print('x'*1000000)",
    }
    try:
        for name, code in tasks.items():
            try:
                result = execute_analysis(settings, [{"message": "synthetic probe"}], code)
                checks[name] = name == "authorized_statistics" and result["result"] == {"count": 1}
            except SandboxUnavailable:
                raise
            except SandboxExecutionError as exc:
                detail = exc.detail
                checks[name] = {
                    "forbidden_file": "PermissionError" in detail.get("stderr", ""),
                    "forbidden_network": "PermissionError" in detail.get("stderr", ""),
                    "wall_timeout": detail["status"] == "timeout",
                    "memory_limit": "MemoryError" in detail.get("stderr", ""),
                    "output_limit": detail.get("exit_code") in {-25, 1},
                }.get(name, False)
        report = {"status": "passed" if all(checks.values()) else "failed", "checks": checks}
    except SandboxUnavailable as exc:
        report = {
            "status": "blocked",
            "checks": checks,
            "reason": str(exc),
            "actual_isolation_verified": False,
        }
    (ROOT / "reports/week8-sandbox.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
