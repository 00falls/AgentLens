import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from agentlens.agent import investigate, read_run
from agentlens.calibration import calibrate, prepare_pack
from agentlens.checkpoints import setup_checkpoints
from agentlens.config import ROOT, Settings
from agentlens.db import create_session
from agentlens.evaluation import evaluate, load_case
from agentlens.executions import execute_recording, execute_scenario, execution_difference
from agentlens.experiments import compare_reports, run_evaluation
from agentlens.frozen import freeze_scenario, read_scenario
from agentlens.gate import evaluate_gate
from agentlens.knowledge import import_runbooks
from agentlens.observability import configure_tracing
from agentlens.recordings import capture_recording
from agentlens.retrieval_experiments import compare_retrieval
from agentlens.run_diff import write_difference
from agentlens.seed import seed


def main():
    parser = argparse.ArgumentParser(prog="agentlens")
    commands = parser.add_subparsers(dest="command", required=True)
    seed_command = commands.add_parser("seed")
    seed_command.add_argument("--dataset", type=Path, default=ROOT / "datasets/telemetry.json")
    commands.add_parser("checkpoint-setup", help="Initialize official checkpoint tables")
    commands.add_parser("knowledge-import", help="Embed and transactionally replace runbooks")
    retrieval = commands.add_parser("retrieval-eval", help="Compare one labeled retrieval query")
    retrieval.add_argument("--case", required=True)
    retrieval.add_argument("--dataset", type=Path, default=ROOT / "datasets/retrieval.jsonl")
    retrieval.add_argument("--report", type=Path, default=ROOT / "reports/week3-retrieval.json")
    invoke = commands.add_parser("invoke")
    invoke.add_argument("--project", required=True)
    invoke.add_argument("--prompt", required=True)
    acceptance = commands.add_parser("acceptance", help="Run exactly one real-model case")
    acceptance.add_argument("--case", default="pool-exhaustion-01")
    acceptance.add_argument("--report", type=Path, default=ROOT / "reports/local/week1.json")
    evaluation = commands.add_parser("eval", help="Evaluate explicitly selected cases")
    selection = evaluation.add_mutually_exclusive_group(required=True)
    selection.add_argument("--case", action="append", dest="case_ids")
    selection.add_argument("--all", action="store_true", help="Explicitly run the full dataset")
    evaluation.add_argument("--dataset", type=Path, default=ROOT / "datasets/dev.jsonl")
    evaluation.add_argument("--name", default="evaluation")
    evaluation.add_argument("--judge", action="store_true", help="Advisory LLM assessment")
    recorded = evaluation.add_mutually_exclusive_group()
    recorded.add_argument("--recorded-run", help="Score one existing run")
    recorded.add_argument("--recorded-file", type=Path, help="Score a single saved run snapshot")
    evaluation.add_argument(
        "--report",
        type=Path,
        default=ROOT / "reports/local" / f"eval-{datetime.now(UTC):%Y%m%dT%H%M%S}.json",
    )
    compare = commands.add_parser(
        "compare", help="Compare reports using the same evaluation contract"
    )
    compare.add_argument("--baseline", type=Path, required=True)
    compare.add_argument("--candidate", type=Path, required=True)
    compare.add_argument("--report", type=Path)
    gate = commands.add_parser("gate", help="Required cases and comparable regression checks")
    gate.add_argument("--baseline", required=True, type=Path)
    gate.add_argument("--candidate", required=True, type=Path)
    gate.add_argument("--policy", type=Path, default=ROOT / "configs/evaluation/gate.json")
    gate.add_argument("--report", required=True, type=Path)
    pack = commands.add_parser("calibration-pack", help="Prepare 12 unlabelled human review probes")
    pack.add_argument("--source", required=True, type=Path)
    pack.add_argument("--output", required=True, type=Path)
    calibration = commands.add_parser("calibrate", help="Compare Judge with genuine human labels")
    calibration.add_argument("--labels", required=True, type=Path)
    calibration.add_argument("--report", required=True, type=Path)
    record = commands.add_parser("record", help="Capture finished tool results; no model call")
    record.add_argument("--run", required=True)
    record.add_argument("--project", required=True)
    freeze = commands.add_parser(
        "freeze-scenario", help="Copy project tool tables into a frozen schema"
    )
    freeze.add_argument("--case", required=True)
    freeze.add_argument("--project", required=True)
    freeze.add_argument("--source-run")
    for name in ["replay", "scenario-eval"]:
        command = commands.add_parser(
            name, help="Call the model with an explicit isolated tool source"
        )
        command.add_argument("--id", required=True)
        command.add_argument("--project", required=True)
        command.add_argument("--model")
        command.add_argument("--report", required=True, type=Path)
    diff = commands.add_parser("run-diff", help="Read saved runs only; no model or tool execution")
    diff.add_argument("--baseline", required=True)
    diff.add_argument("--candidate", required=True)
    diff.add_argument("--project", required=True)
    diff.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    settings = Settings()
    if args.command in {"invoke", "eval", "acceptance", "replay", "scenario-eval"}:
        configure_tracing("agentlens-cli")
    if args.command == "record":
        result = asyncio.run(
            capture_recording(settings, args.run, args.project),
            loop_factory=asyncio.SelectorEventLoop,
        )
        print(json.dumps({k: v for k, v in result.items() if k != "payload"}))
        return
    if args.command == "freeze-scenario":
        result = freeze_scenario(settings, args.case, args.project, args.source_run)
        print(
            json.dumps(
                {"scenario_id": result["scenario_id"], "sha256": result["manifest"]["sha256"]}
            )
        )
        return
    if args.command in {"replay", "scenario-eval"}:
        execute = execute_recording if args.command == "replay" else execute_scenario
        result = asyncio.run(
            execute(settings, args.id, args.project, args.model),
            loop_factory=asyncio.SelectorEventLoop,
        )
        with create_session(settings) as session:
            run = read_run(session, result["run_id"], args.project)
            case = (
                read_scenario(session, run["scenario_id"], args.project)["manifest"]["case"]
                if run["scenario_id"]
                else None
            )
        verdict = evaluate(case, run) if case else None
        if run["source_run_id"]:
            report = execution_difference(
                settings, run["source_run_id"], run["run_id"], args.project
            )
            write_difference(report, args.report)
            if report["evaluation"] is not None:
                verdict = report["evaluation"]["candidate"]
        else:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps({"run": run, "evaluation": verdict}, ensure_ascii=False, indent=2)
                + "\n",
                encoding="utf-8",
            )
        print(
            json.dumps(
                {
                    "run_id": run["run_id"],
                    "status": run["status"],
                    "execution_mode": run["execution_mode"],
                }
            )
        )
        raise SystemExit(
            3
            if run["status"] == "replay_mismatch"
            else 2
            if run["status"] == "failed"
            else 1
            if verdict is not None and not verdict["passed"]
            else 0
        )
    if args.command == "run-diff":
        report = execution_difference(settings, args.baseline, args.candidate, args.project)
        write_difference(report, args.report)
        print(json.dumps({"baseline": args.baseline, "candidate": args.candidate}))
        return
    if args.command == "checkpoint-setup":
        print(
            json.dumps(
                asyncio.run(setup_checkpoints(settings), loop_factory=asyncio.SelectorEventLoop),
                indent=2,
            )
        )
        return
    if args.command == "eval":
        try:
            result = asyncio.run(
                run_evaluation(
                    settings,
                    args.dataset,
                    args.case_ids,
                    args.name,
                    args.report,
                    args.recorded_run,
                    args.judge,
                    args.recorded_file,
                ),
                loop_factory=asyncio.SelectorEventLoop,
            )
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
        raise SystemExit(
            2
            if result["summary"]["errors"] or result["summary"]["judge_errors"]
            else int(bool(result["summary"]["failed"]))
        )
    if args.command == "calibration-pack":
        print(json.dumps(prepare_pack(args.source, args.output)))
        return
    if args.command == "calibrate":
        result = asyncio.run(
            calibrate(settings, args.labels, args.report), loop_factory=asyncio.SelectorEventLoop
        )
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "criterion_agreement": result.get("criterion_agreement"),
                }
            )
        )
        raise SystemExit(0 if result["status"] == "complete" else 2)
    if args.command == "gate":
        try:
            result = evaluate_gate(args.baseline, args.candidate, args.policy)
        except ValueError as exc:
            parser.error(str(exc))
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {"passed": result["passed"], "failures": result["failures"]}, ensure_ascii=False
            )
        )
        raise SystemExit(0 if result["passed"] else 1)
    if args.command == "compare":
        try:
            result = compare_reports(args.baseline, args.candidate)
        except ValueError as exc:
            parser.error(str(exc))
        content = json.dumps(result, ensure_ascii=False, indent=2)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(content + "\n", encoding="utf-8")
        print(content)
        return
    with create_session(settings) as session:
        if args.command == "seed":
            result = seed(session, args.dataset)
        elif args.command == "knowledge-import":
            result = import_runbooks(session, settings)
        elif args.command == "retrieval-eval":
            result = compare_retrieval(session, settings, args.dataset, args.case, args.report)
        elif args.command == "invoke":
            result = asyncio.run(
                investigate(settings, args.project, args.prompt),
                loop_factory=asyncio.SelectorEventLoop,
            )
        else:
            case = load_case(args.case)
            result = asyncio.run(
                investigate(settings, case["project_id"], case["input"]),
                loop_factory=asyncio.SelectorEventLoop,
            )
            run = read_run(session, result["run_id"])
            result = {"case_id": case["case_id"], "evaluation": evaluate(case, run), "run": run}
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.command == "acceptance" and not result["evaluation"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
