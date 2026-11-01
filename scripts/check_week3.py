"""Real local components; no new business runs or chat-provider requests."""

import asyncio
import json

import numpy as np
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from langchain.mcp import MCPAdapter
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.dialects import postgresql

from agentlens.config import ROOT, Settings
from agentlens.db import KnowledgeChunk, KnowledgeDocument, create_session
from agentlens.evaluation import evaluate, load_case, load_cases
from agentlens.knowledge import QUERY_PREFIX, corpus, embedding_model
from agentlens.retrieval_experiments import retrieval_scores
from agentlens.schemas import RunbookQuery


async def main():
    settings = Settings()
    docs, chunks, manifest = corpus()
    checks = {
        "18_documents_36_chunks": len(docs) == 18 and len(chunks) == 36,
        "unique_chunk_ids": len({c["id"] for c in chunks}) == len(chunks),
    }
    known_docs = {d["id"] for d in docs}
    checks["chunk_documents_exist"] = all(c["document_id"] in known_docs for c in chunks)
    case = load_cases(ROOT / "datasets/week3.jsonl")[0]
    checks["relevance_labels_exist"] = set(case["relevant_chunk_ids"]) <= {c["id"] for c in chunks}
    model = embedding_model(str(settings.embedding_path))
    lengths = [len(model.tokenizer.encode(c["content"])) for c in chunks]
    checks["no_embedding_truncation"] = max(lengths) <= model.max_seq_length
    vectors = model.encode(
        [chunks[0]["content"], QUERY_PREFIX + "order-api HikariPool 连接获取超时"],
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    checks["real_bge_512_finite_normalized"] = (
        vectors.shape == (2, 512)
        and bool(np.isfinite(vectors).all())
        and bool(np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5))
    )
    sql = str(
        select(KnowledgeChunk.id)
        .join(KnowledgeDocument)
        .where(KnowledgeDocument.project_id == "project-a")
        .order_by(KnowledgeChunk.embedding.cosine_distance(vectors[0].tolist()))
        .limit(3)
        .compile(dialect=postgresql.dialect())
    )
    checks["postgres_vector_scope_sql_compiles"] = "<=>" in sql and sql.index("WHERE") < sql.index(
        "LIMIT"
    )
    # Rescore an actual old run: retrieval rows must not be treated as timestamped telemetry.
    old_run = json.loads((ROOT / "reports/week1-acceptance.json").read_text(encoding="utf-8"))[
        "run"
    ]
    old_case = load_case("pool-exhaustion-01")
    checks["historical_run_still_scores"] = evaluate(old_case, old_run)["passed"]
    extended = json.loads(json.dumps(old_run))
    row = {"evidence_id": "pool-exhaustion--s01", "project_id": "project-a"}
    extended["steps"].append(
        {
            "kind": "tool",
            "name": "search_runbooks",
            "input": {"query": "HikariPool"},
            "output": {"chunks": [row]},
        }
    )
    extended["output"]["evidence_ids"].append(row["evidence_id"])
    checks["handbook_rows_are_not_time_window_rows"] = evaluate(case, extended)["passed"]
    extended["output"]["evidence_ids"].append("not-retrieved")
    checks["fabricated_citation_fails_scoring"] = not evaluate(case, extended)["checks"][
        "valid_citations"
    ]
    extended["output"]["evidence_ids"].pop()
    row["project_id"] = "project-b"
    checks["cross_project_handbook_fails_scoring"] = not evaluate(case, extended)["checks"][
        "knowledge_project_scope"
    ]
    checks["retrieval_metric_contract"] = retrieval_scores(["a", "b"], ["c", "a"]) == {
        "hit_at_k": 1,
        "recall_at_k": 0.5,
    } and retrieval_scores(["a"], []) == {"hit_at_k": 0, "recall_at_k": 0.0}
    try:
        RunbookQuery(query="", top_k=0)
    except ValidationError:
        checks["query_boundary_rejects_invalid_input"] = True
    else:
        checks["query_boundary_rejects_invalid_input"] = False
    for project in ["project-a", None]:
        headers = {} if project is None else {"x-agentlens-project": project}
        async with MCPAdapter(
            Client(StreamableHttpTransport(settings.mcp_url, headers=headers), timeout=10)
        ) as adapter:
            tools = {t.name: t for t in await adapter.list_tools()}
            checks["knowledge_mcp_tools_discovered"] = {
                "search_logs",
                "query_metrics",
                "search_runbooks",
            } <= set(tools)
            checks["project_hidden_from_model"] = all(
                "project_id" not in tool.args_schema["properties"] for tool in tools.values()
            )
            message = await tools["search_runbooks"].ainvoke(
                {
                    "name": "search_runbooks",
                    "id": "week3-boundary",
                    "type": "tool_call",
                    "args": {"query": "" if project else "HikariPool", "top_k": 3},
                }
            )
            checks["invalid_query_rejected_over_mcp" if project else "missing_scope_rejected"] = (
                message.status == "error"
            )
    with create_session(settings) as session:
        checks["postgres_keyword_rank_works"] = (
            session.scalar(
                text(
                    "SELECT ts_rank_cd(to_tsvector('simple', "
                    "regexp_replace(:content, '[^a-zA-Z0-9_-]+', ' ', 'g')), "
                    "websearch_to_tsquery('simple', :query))"
                ),
                {"content": chunks[0]["content"], "query": "HikariPool OR db_pool_waiters"},
            )
            > 0
        )
        database = {
            "server_version": session.scalar(text("SHOW server_version")),
            "vector_available": session.scalar(
                text("SELECT count(*) FROM pg_available_extensions WHERE name='vector'")
            )
            > 0,
            "migration": session.scalar(text("SELECT version_num FROM alembic_version")),
        }
    result = {
        "status": "checks_passed" if all(checks.values()) else "checks_failed",
        "checks": checks,
        "chat_model_calls": 0,
        "new_business_runs": 0,
        "corpus_manifest": manifest,
        "maximum_section_tokens": max(lengths),
        "database": database,
        "pgvector_query_executed": False,
        "note": "Evaluator fixtures are mutated copies, not new Agent runs or quality results.",
    }
    (ROOT / "reports/week3-checks.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    assert all(checks.values()), checks


if __name__ == "__main__":
    asyncio.run(main())
