"""Run only the frozen ten-case Flash subset, or gate two saved batches."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from agentlens.ci_evaluation import evaluate_ci_gate, run_ci_evaluation
from agentlens.config import Settings
from agentlens.observability import configure_tracing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--gate-only", type=Path, help="Candidate saved batch; no provider calls")
    args = parser.parse_args()
    if args.gate_only and not args.baseline:
        parser.error("--gate-only requires --baseline")
    if args.gate_only:
        result = evaluate_ci_gate(args.baseline, args.gate_only)
    else:
        configure_tracing("agentlens-ci-evaluation")
        options = {} if os.name == "posix" else {"loop_factory": asyncio.SelectorEventLoop}
        report = asyncio.run(run_ci_evaluation(Settings(), args.report), **options)
        if not args.baseline:
            return 0 if report["summary"]["complete"] else 2
        result = evaluate_ci_gate(args.baseline, args.report)
        args.report = args.report.with_name(args.report.stem + "-gate.json")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"passed": result["passed"], "failures": result["failures"]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
