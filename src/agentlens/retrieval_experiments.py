"""Compare retrieval only: one factor, no chat-model calls or answer labels in tools."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from agentlens.config import ROOT, Settings
from agentlens.knowledge import corpus, search_runbooks
from agentlens.schemas import RunbookQuery


class RetrievalCase(BaseModel):
    case_id: str
    project_id: str
    query: str = Field(min_length=1, max_length=2000)
    relevant_chunk_ids: list[str] = Field(min_length=1)


def retrieval_scores(relevant: list[str], returned: list[str]) -> dict:
    matches = set(relevant) & set(returned)
    return {"hit_at_k": int(bool(matches)), "recall_at_k": len(matches) / len(set(relevant))}


def compare_retrieval(
    session: Session, settings: Settings, dataset: Path, case_id: str, report: Path
) -> dict:
    cases = [
        RetrievalCase.model_validate_json(line)
        for line in dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Retrieval case IDs must be unique")
    case = next((case for case in cases if case.case_id == case_id), None)
    if case is None:
        raise ValueError(f"Unknown retrieval case: {case_id}")
    docs, chunks, source_manifest = corpus()
    allowed_docs = {doc["id"] for doc in docs if doc["project_id"] == case.project_id}
    allowed_chunks = {chunk["id"] for chunk in chunks if chunk["document_id"] in allowed_docs}
    if not set(case.relevant_chunk_ids) <= allowed_chunks:
        raise ValueError("Relevance labels must belong to this project's corpus")
    results = {}
    for strategy in ["vector", "hybrid"]:
        rows = search_runbooks(
            session, settings, case.project_id, RunbookQuery(query=case.query, top_k=3), strategy
        )["chunks"]
        results[strategy] = {
            "scores": retrieval_scores(case.relevant_chunk_ids, [r["evidence_id"] for r in rows]),
            "chunks": rows,
        }
    manifests = [
        {k: v for k, v in row["retrieval_manifest"].items() if k != "strategy"}
        for result in results.values()
        for row in result["chunks"]
    ]
    if not manifests or any(m != manifests[0] for m in manifests):
        raise ValueError("Comparison requires a populated, single-version knowledge corpus")
    if any(manifests[0][key] != value for key, value in source_manifest.items()):
        raise ValueError("Indexed corpus differs from relevance-label sources; reimport runbooks")
    baseline, candidate = (results[strategy]["scores"] for strategy in ["vector", "hybrid"])
    delta = {key: candidate[key] - baseline[key] for key in baseline}
    changed = ["improved" if d > 0 else "regressed" for d in delta.values() if d]
    outcome = "unchanged" if not changed else changed[0] if len(set(changed)) == 1 else "mixed"
    result = {
        "schema_version": 1,
        "status": "complete",
        "created_at": datetime.now(UTC).isoformat(),
        "case": case.model_dump(),
        "selected_cases": 1,
        "chat_model_calls": 0,
        "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "retrieval_code_sha256": hashlib.sha256(
            (ROOT / "src/agentlens/knowledge.py").read_bytes()
        ).hexdigest(),
        "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "fixed_manifest": manifests[0],
        "changed_factor": "vector vs vector+keyword RRF",
        "results": results,
        "delta": delta,
        "outcome": outcome,
        "limitation": "One synthetic development case; no aggregate quality claim.",
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report.with_suffix(".md").write_text(
        f"# 检索对比：{case_id}\n\n只改变检索策略；固定语料、切分、模型与 Top-K=3。\n\n"
        "| 策略 | Hit@3 | Recall@3 |\n|---|---:|---:|\n"
        + "".join(
            f"| {s} | {r['scores']['hit_at_k']} | {r['scores']['recall_at_k']:.3f} |\n"
            for s, r in results.items()
        )
        + f"\n结果：{outcome}。只有一条合成开发用例，不代表整体质量。\n",
        encoding="utf-8",
    )
    return result
