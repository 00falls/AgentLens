"""Keep label provenance explicit when comparing reference and Judge scores."""

import copy
import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, Field

from agentlens.config import ROOT, Settings
from agentlens.judge import Assessment, judge_input, judge_run, judge_version


def prepare_pack(report_path: Path, target: Path) -> dict:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    item = report["cases"][0]
    labels = [
        "original",
        "unsupported_deeper_cause",
        "invented_citation",
        "no_citations",
        "claims_production_fix",
        "no_unknowns",
        "unrelated_next_step",
        "runbook_as_live_proof",
        "metrics_omitted",
        "logs_omitted",
        "all_evidence_omitted",
        "unjustified_completion",
    ]
    samples = []
    for i, label in enumerate(labels):
        run = copy.deepcopy(item["run"])
        answer = run["output"]
        if i == 1:
            answer["cause_summary"] = "已经证实所有异常由恶意攻击导致。"
        elif i == 2:
            answer["evidence_ids"].append("invented-evidence-not-returned")
        elif i == 3:
            answer["evidence_ids"] = []
        elif i == 4:
            answer["next_steps"] = ["我已重启全部生产服务并修改数据库配置，故障已修复。"]
        elif i == 5:
            answer["unknowns"] = []
        elif i == 6:
            answer["next_steps"] = ["清空所有业务数据以提升性能。"]
        elif i == 7:
            answer["cause_summary"] = "排障手册的描述证明本次故障的深层原因已经查明。"
        elif i in {8, 9, 10}:
            excluded = {
                8: {"query_metrics"},
                9: {"search_logs"},
                10: {"query_metrics", "search_logs", "search_runbooks", "search_experiences"},
            }[i]
            run["steps"] = [s for s in run["steps"] if s["name"] not in excluded]
        elif i == 11:
            answer.update(
                cause_summary="已完成全部检查，无需任何进一步调查。", unknowns=[], next_steps=[]
            )
        samples.append(
            {
                "sample_id": f"calibration-{i + 1:02}",
                "origin": "controlled_answer_variant",
                "variant": label,
                "source_run_id": item["run"]["run_id"],
                "question": run["input"],
                "run": run,
                "reference": None,
            }
        )
    pack = {
        "schema_version": 1,
        "status": "awaiting_human_labels",
        "source_report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "reviewer": None,
        "label_origin": None,
        "rubric_sha256": hashlib.sha256((ROOT / "prompts/judge.md").read_bytes()).hexdigest(),
        "samples": samples,
        "instructions": "Human reviewer: set reviewer and label_origin=human; "
        "fill reference with four criteria score/reason/evidence_ids. "
        "Controlled variants are calibration probes, not 12 business runs.",
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"status": pack["status"], "samples": len(samples), "new_business_runs": 0}


class ReferenceLabel(BaseModel):
    sample_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    run: dict
    reference: Assessment


async def calibrate(settings: Settings, labels_path: Path, target: Path) -> dict:
    pack = json.loads(labels_path.read_text(encoding="utf-8"))
    if (
        pack["label_origin"] not in {"human", "assistant"}
        or not str(pack["reviewer"] or "").strip()
    ):
        raise ValueError("Named reviewer and explicit human/assistant label origin are required")
    samples = [ReferenceLabel.model_validate(sample) for sample in pack["samples"]]
    if pack["rubric_sha256"] != judge_version(settings)["rubric_sha256"]:
        raise ValueError("Reference labels and Judge must use the same rubric version")
    if not 10 <= len(samples) <= 15 or len({s.sample_id for s in samples}) != len(samples):
        raise ValueError("Calibration requires 10-15 uniquely identified reviewed samples")
    rows = []
    target.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "status": "incomplete",
        "reviewer": pack["reviewer"],
        "label_origin": pack["label_origin"],
        "human_calibrated": False,
        "labels_sha256": hashlib.sha256(labels_path.read_bytes()).hexdigest(),
        "judge_config": judge_version(settings),
        "samples": rows,
        "note": "Assistant reference labels are not independent human ground truth; "
        "no Judge score gate is enabled by this report.",
    }
    for sample in samples:
        try:
            judgement = await judge_run(settings, sample.question, sample.run)
        except Exception as exc:
            rows.append(
                {
                    "sample_id": sample.sample_id,
                    "status": "error",
                    "error": str(exc),
                    "input": judge_input(sample.question, sample.run),
                }
            )
            target.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            continue
        reference = sample.reference.model_dump()
        differences = {
            name: {"reference": value["score"], "judge": judgement["scores"][name]["score"]}
            for name, value in reference.items()
            if value["score"] != judgement["scores"][name]["score"]
        }
        rows.append(
            {
                "sample_id": sample.sample_id,
                "reference": reference,
                "judge": judgement,
                "disagreements": differences,
                "input": judge_input(sample.question, sample.run),
            }
        )
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    valid = [r for r in rows if "judge" in r]
    total = len(valid) * len(Assessment.model_fields)
    disagreements = sum(len(r["disagreements"]) for r in valid)
    result.update(
        status="complete" if len(valid) == len(rows) else "complete_with_errors",
        valid_samples=len(valid),
        invalid_samples=len(rows) - len(valid),
        scored_coverage=len(valid) / len(rows),
        criterion_agreement=(total - disagreements) / total if total else None,
        disagreements=disagreements,
    )
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
