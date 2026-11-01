"""Keep week 1/2 datasets frozen; extend exactly one business case for week 3."""

import json

from agentlens.config import ROOT
from agentlens.evaluation import load_case


def main():
    case = load_case("pool-exhaustion-01")
    case["input"] += "请检索相关排障手册，引用支持检查建议的手册片段。"
    case["required_tools"].append("search_runbooks")
    case["relevant_chunk_ids"] = ["pool-exhaustion--s01", "pool-exhaustion--s02"]
    target = ROOT / "datasets/week3.jsonl"
    target.write_text(json.dumps(case, ensure_ascii=False) + "\n", encoding="utf-8")
    retrieval = {
        "case_id": "pool-exhaustion-retrieval-01",
        "project_id": case["project_id"],
        "query": "order-api HikariPool connection acquisition timed out after 30000ms; "
        "active=20 idle=0 max=20，db_pool_waiters 升高，如何排查？",
        "relevant_chunk_ids": case["relevant_chunk_ids"],
    }
    (ROOT / "datasets/retrieval.jsonl").write_text(
        json.dumps(retrieval, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("Generated one business case and its retrieval-only query")


if __name__ == "__main__":
    main()
