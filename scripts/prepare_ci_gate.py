"""Select paid changes and freeze the gate inputs from the trusted base commit."""

import json
import os
import subprocess
from pathlib import Path


def git(*args):
    return subprocess.check_output(["git", *args])


def main():
    base = os.environ["BASE_SHA"]
    head = os.environ["HEAD_SHA"]
    initial = not base or set(base) == {"0"}
    paths = (
        (
            git("ls-tree", "-r", "--name-only", head)
            if initial
            else git("diff", "--name-only", base, head)
        )
        .decode("utf-8")
        .splitlines()
    )
    previous = os.environ.get("PREVIOUS_SHA", "")
    # A restore commit can equal the PR base; the prior head still changed the Prompt.
    if previous and set(previous) != {"0"}:
        paths += git("diff", "--name-only", previous, head).decode("utf-8").splitlines()
    prefixes = ("src/", "prompts/", "datasets/", "configs/", "scripts/", "migrations/", ".github/")
    relevant = any(
        path.startswith(prefixes) or path in {"pyproject.toml", "uv.lock", ".gitattributes"}
        for path in paths
    )
    trusted = head if initial else base
    for path in ["configs/evaluation/ci-cases.json", "configs/evaluation/ci-gate.json"]:
        if git("show", f"{trusted}:{path}") != Path(path).read_bytes():
            raise ValueError(f"Gate input changed from trusted base: {path}")
    target = Path(".tools/ci-baseline.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(git("show", f"{trusted}:reports/ci/local-baseline.json"))
    print(json.dumps({"paid_evaluation": relevant, "base": trusted, "candidate": head}))
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
        stream.write(f"relevant={str(relevant).lower()}\n")


if __name__ == "__main__":
    main()
