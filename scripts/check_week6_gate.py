"""Known regression lives only in labelled experiment snapshots, never in the agent."""

import copy
import json
import subprocess
import sys

from agentlens.config import ROOT
from agentlens.evaluation import evaluate, load_cases


def main():
    source = ROOT / "reports/experiments/week6-candidate.json"
    original = json.loads(source.read_text(encoding="utf-8"))
    assert original["summary"]["passed"] == 1
    directory = ROOT / "reports/week6-gate-demonstration"
    directory.mkdir(parents=True, exist_ok=True)
    bad = copy.deepcopy(original)
    bad["execution_kind"] = "controlled_snapshot_mutation"
    bad["name"] = "Controlled invalid citation; no new model execution"
    item = bad["cases"][0]
    item["run"]["output"]["evidence_ids"].append("controlled-never-returned-evidence")
    case = next(
        c for c in load_cases(ROOT / "datasets/week6/dev.jsonl") if c["case_id"] == item["case_id"]
    )
    item["evaluation"] = evaluate(case, item["run"])
    item["outcome"] = "failed"
    item["judge"] = {"status": "invalidated_by_controlled_answer_mutation"}
    bad["summary"].update(passed=0, failed=1, pass_rate=0)
    broken = directory / "broken.json"
    restored = directory / "restored.json"
    broken.write_text(json.dumps(bad, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fixed = copy.deepcopy(original)
    fixed["execution_kind"] = "controlled_restoration_of_recorded_snapshot"
    restored.write_text(json.dumps(fixed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    outcomes = []
    for candidate, expected in [(broken, 1), (restored, 0)]:
        report = directory / f"{candidate.stem}-gate.json"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "agentlens.cli",
                "gate",
                "--baseline",
                str(source),
                "--candidate",
                str(candidate),
                "--report",
                str(report),
            ],
            cwd=ROOT,
            capture_output=True,
        )
        (directory / f"{candidate.stem}.log").write_bytes(result.stdout + result.stderr)
        outcomes.append(
            {
                "variant": candidate.stem,
                "actual_exit_code": result.returncode,
                "expected_exit_code": expected,
            }
        )
    summary = {
        "passed": all(r["actual_exit_code"] == r["expected_exit_code"] for r in outcomes),
        "execution_kind": "controlled_snapshot_mutation_and_restoration",
        "new_business_runs": 0,
        "provider_requests": 0,
        "checks": outcomes,
        "source_run_id": original["cases"][0]["run"]["run_id"],
    }
    (ROOT / "reports/week6-gate-demo.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary))
    assert summary["passed"]


if __name__ == "__main__":
    main()
