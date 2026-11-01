"""Own the evaluation services, run one batch, and close only the processes we started."""

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from agentlens.config import ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    directory = ROOT / "reports/local/ci-services"
    directory.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "NO_PROXY": "127.0.0.1,localhost", "PYTHONIOENCODING": "utf-8"}
    collector = ROOT / ".tools/otelcol" / ("otelcol.exe" if os.name == "nt" else "otelcol")
    commands = [
        ("telemetry", 8001, [sys.executable, "scripts/run_telemetry.py"]),
        ("collector", 4318, [str(collector), "--config=configs/observability/collector.yaml"]),
        ("gateway", 4000, [sys.executable, "scripts/run_gateway.py"]),
        (
            "mcp",
            8010,
            [
                sys.executable,
                "-m",
                "uvicorn",
                "agentlens.mcp_server:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8010",
            ],
        ),
    ]
    handles, processes = [], []
    try:
        for name, port, command in commands:
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    raise RuntimeError(
                        f"Port {port} is occupied; refusing to reuse another service"
                    )
            handle = (directory / f"{name}.log").open("wb")
            handles.append(handle)
            processes.append(
                subprocess.Popen(
                    command,
                    cwd=ROOT,
                    env=env,
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            )
        deadline = time.monotonic() + 90
        while True:
            if any(p.poll() is not None for p in processes):
                raise RuntimeError("Evaluation service exited; inspect reports/local/ci-services")
            pending = []
            for _, port, _ in commands:
                with socket.socket() as probe:
                    probe.settimeout(0.2)
                    if probe.connect_ex(("127.0.0.1", port)):
                        pending.append(port)
            if not pending:
                break
            if time.monotonic() > deadline:
                raise RuntimeError(f"Evaluation services did not become ready: {pending}")
            time.sleep(0.5)
        command = [sys.executable, "scripts/run_ci_eval.py", "--report", str(args.report)]
        if args.baseline:
            command += ["--baseline", str(args.baseline)]
        return subprocess.call(command, cwd=ROOT, env=env)
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=True,
                    )
                else:
                    process.terminate()
                process.wait(timeout=15)
        for handle in handles:
            handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
