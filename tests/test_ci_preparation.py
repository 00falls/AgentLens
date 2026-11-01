"""Exercise CI change detection against real Git commits, without model calls."""

import os
import subprocess
import sys

import pytest

from agentlens.config import ROOT


@pytest.mark.parametrize("restore", [False, True])
def test_restoration_runs_eval_but_document_only_change_does_not(tmp_path, restore):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path).decode().strip()

    git("init", "--quiet")
    git("config", "user.name", "CI contract test")
    git("config", "user.email", "ci@example.invalid")
    git("config", "core.autocrlf", "false")
    for path in [
        "configs/evaluation/ci-cases.json",
        "configs/evaluation/ci-gate.json",
        "reports/ci/local-baseline.json",
        "prompts/diagnose.md",
    ]:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"frozen\n")
    git("add", ".")
    git("commit", "--quiet", "-m", "base")
    base = git("rev-parse", "HEAD")
    if restore:
        (tmp_path / "prompts/diagnose.md").write_bytes(b"controlled regression\n")
        git("commit", "--quiet", "-am", "regress")
        previous = git("rev-parse", "HEAD")
        (tmp_path / "prompts/diagnose.md").write_bytes(b"frozen\n")
    else:
        previous = base
        (tmp_path / "README.md").write_text("document only\n")
    git("add", ".")
    git("commit", "--quiet", "-m", "restore" if restore else "document")
    output = tmp_path / "github-output"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/prepare_ci_gate.py")],
        cwd=tmp_path,
        env={
            **os.environ,
            "BASE_SHA": base,
            "HEAD_SHA": git("rev-parse", "HEAD"),
            "PREVIOUS_SHA": previous,
            "GITHUB_OUTPUT": str(output),
        },
        check=True,
    )
    assert output.read_text().strip() == f"relevant={str(restore).lower()}"
    assert (tmp_path / ".tools/ci-baseline.json").read_bytes() == b"frozen\n"
