"""Only OpenShell executes generated code; this module never evaluates it on the host."""

import hashlib
import json
import shutil
import subprocess
from uuid import uuid4

from sqlalchemy import select

from agentlens.config import ROOT
from agentlens.db import Run, RunStep, create_session
from agentlens.schemas import AnalysisQuery


class SandboxUnavailable(RuntimeError):
    pass


class AnalysisAccessDenied(ValueError):
    pass


class SandboxExecutionError(RuntimeError):
    def __init__(self, detail):
        self.detail = detail
        super().__init__(json.dumps(detail))


def authorized_logs(settings, project, run_id, request: AnalysisQuery):
    with create_session(settings) as session:
        run = session.scalar(select(Run).where(Run.id == run_id, Run.project_id == project))
        if run is None:
            raise AnalysisAccessDenied("Analysis requires a run in the authorized project")
        rows = {}
        for step in session.scalars(
            select(RunStep).where(
                RunStep.run_id == run_id, RunStep.name == "search_logs", RunStep.error.is_(None)
            )
        ):
            for row in (step.output or {}).get("logs", []):
                rows[row["evidence_id"]] = row
        if set(request.evidence_ids) - rows.keys():
            raise AnalysisAccessDenied(
                "Analysis input must reference logs already retrieved in this run"
            )
        return [rows[eid] for eid in request.evidence_ids]


def execute_analysis(settings, logs, code):
    binary = shutil.which(settings.openshell_binary)
    if binary is None:
        raise SandboxUnavailable("OpenShell CLI/gateway required; host execution is prohibited")
    name = f"al-{uuid4().hex[:16]}"
    base = [binary, "sandbox"]
    policy = ROOT / "configs/sandbox/policy.yaml"
    payload = json.dumps({"logs": logs, "code": code}, ensure_ascii=False)
    if len(payload.encode()) > 128_000:
        raise ValueError("Selected log input exceeds the 128000-byte analysis budget")
    try:
        subprocess.run(
            [
                *base,
                "create",
                "--name",
                name,
                "--from",
                settings.sandbox_image,
                "--policy",
                str(policy),
                "--cpu",
                "1",
                "--memory",
                "512Mi",
                "--no-auto-providers",
                "--detach",
                "--",
                "/bin/sleep",
                "180",
            ],
            check=True,
            timeout=90,
            capture_output=True,
        )
        result = subprocess.run(
            [
                *base,
                "exec",
                "-n",
                name,
                "--timeout",
                "15",
                "--no-tty",
                "--no-login-shell",
                "--",
                "/usr/local/bin/python",
                "/app/worker.py",
            ],
            input=payload,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=30,
            check=True,
        )
        output = json.loads(result.stdout)
        if output["status"] != "ok":
            raise SandboxExecutionError(output)
        return output
    finally:
        # Also terminate remote children after timeout; killing the CLI alone is insufficient.
        subprocess.run([*base, "delete", name], check=True, timeout=30, capture_output=True)


def analysis_result(settings, project, run_id, request):
    logs = authorized_logs(settings, project, run_id, request)
    output = execute_analysis(settings, logs, request.python_code)
    return {
        "analyses": [
            {
                "evidence_id": f"analysis-{uuid4()}",
                "source_evidence_ids": request.evidence_ids,
                "code_sha256": hashlib.sha256(request.python_code.encode()).hexdigest(),
                "result": output["result"],
                "runtime": "openshell",
            }
        ]
    }
