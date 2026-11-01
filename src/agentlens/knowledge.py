"""Fixed section chunks, local BGE embeddings, and project-scoped pgvector search."""

import hashlib
import json
import re
from functools import lru_cache
from typing import Literal

from opentelemetry import trace
from sqlalchemy import delete, func, literal_column, select
from sqlalchemy.orm import Session

from agentlens.config import ROOT, Settings
from agentlens.db import KnowledgeChunk, KnowledgeDocument
from agentlens.schemas import RunbookQuery

EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
EMBEDDING_REVISION = "7999e1d3359715c523056ef9478215996d62a620"
QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："
CANDIDATE_K = 10
RRF_OFFSET = 60


def corpus() -> tuple[list[dict], list[dict], dict]:
    catalog = json.loads((ROOT / "datasets/runbooks/catalog.json").read_text(encoding="utf-8"))
    documents, chunks = [], []
    for entry in catalog["documents"]:
        source = f"datasets/runbooks/{entry['id']}.md"
        content = (ROOT / source).read_text(encoding="utf-8")
        document = {
            "id": entry["id"],
            "project_id": entry["project_id"],
            "title": entry["title"],
            "source": source,
            "revision": hashlib.sha256(content.encode()).hexdigest(),
            "kind": "runbook",
        }
        documents.append(document)
        # These authored handbooks have bounded, self-contained H2 sections.
        for index, section in enumerate(content.split("\n## ")[1:], start=1):
            chunks.append(
                {
                    "id": f"{entry['id']}--s{index:02}",
                    "document_id": entry["id"],
                    "content": f"{entry['title']}\n{section.strip()}",
                }
            )
    manifest = {
        "corpus_sha256": hashlib.sha256(
            json.dumps(documents, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest(),
        "chunks_sha256": hashlib.sha256(
            json.dumps(chunks, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest(),
        "chunking": "authored-h2-v1",
        "embedding_model": EMBEDDING_MODEL,
        "embedding_revision": EMBEDDING_REVISION,
        "dimensions": 512,
        "normalize": True,
        "query_prefix": QUERY_PREFIX,
        "max_seq_length": 512,
    }
    return documents, chunks, manifest


@lru_cache
def embedding_model(path: str):
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(path, device="cpu", local_files_only=True)
    if model.get_sentence_embedding_dimension() != 512:
        raise ValueError("The fixed BGE embedding contract requires 512 dimensions")
    model.max_seq_length = 512
    return model


def import_runbooks(session: Session, settings: Settings) -> dict:
    documents, chunks, manifest = corpus()
    model = embedding_model(str(settings.embedding_path))
    # Keep all source text: truncation would invalidate section-level retrieval labels.
    texts = [chunk["content"] for chunk in chunks]
    lengths = [len(model.tokenizer.encode(text)) for text in texts]
    if max(lengths) > model.max_seq_length:
        raise ValueError("A runbook section exceeds the fixed embedding token limit")
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    manifest["artifacts_sha256"] = hashlib.sha256(
        (settings.embedding_path / "artifacts.json").read_bytes()
    ).hexdigest()
    runbook_ids = select(KnowledgeDocument.id).where(KnowledgeDocument.kind == "runbook")
    session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id.in_(runbook_ids)))
    session.execute(delete(KnowledgeDocument).where(KnowledgeDocument.kind == "runbook"))
    session.add_all(KnowledgeDocument(**document) for document in documents)
    session.flush()
    session.add_all(
        KnowledgeChunk(**chunk, embedding=vector.tolist(), manifest=manifest)
        for chunk, vector in zip(chunks, embeddings, strict=True)
    )
    session.commit()
    return {"documents": len(documents), "chunks": len(chunks), "manifest": manifest}


@trace.get_tracer("agentlens.knowledge").start_as_current_span("knowledge.search_runbooks")
def search_runbooks(
    session: Session,
    settings: Settings,
    project_id: str,
    query: RunbookQuery,
    strategy: Literal["vector", "hybrid"] = "vector",
) -> dict[str, list[dict]]:
    model = embedding_model(str(settings.embedding_path))
    vector = model.encode(QUERY_PREFIX + query.query, normalize_embeddings=True).tolist()
    scoped = (
        select(KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
        .where(KnowledgeDocument.project_id == project_id)
    )
    # Both candidate lists are filtered before LIMIT, so another project cannot consume Top-K.
    vector_rows = session.execute(
        scoped.order_by(KnowledgeChunk.embedding.cosine_distance(vector), KnowledgeChunk.id).limit(
            CANDIDATE_K
        )
    ).all()
    artifacts_sha256 = hashlib.sha256(
        (settings.embedding_path / "artifacts.json").read_bytes()
    ).hexdigest()
    if any(row[0].manifest["artifacts_sha256"] != artifacts_sha256 for row in vector_rows):
        raise ValueError(
            "Query embedding artifacts differ from indexed documents; reimport runbooks"
        )
    keyword_rows = []
    terms = sorted(set(re.findall(r"[A-Za-z][A-Za-z0-9_-]*|(?<!\d)\d{3}(?!\d)", query.query)))
    if strategy == "hybrid" and terms:
        config = literal_column("'simple'")
        # PostgreSQL simple parsing joins Latin terms across some Chinese punctuation.
        technical_text = func.regexp_replace(KnowledgeChunk.content, "[^a-zA-Z0-9_-]+", " ", "g")
        tokens = func.to_tsvector(config, technical_text)
        tsquery = func.websearch_to_tsquery(config, " OR ".join(terms))
        keyword_rows = session.execute(
            scoped.where(tokens.op("@@")(tsquery))
            .order_by(func.ts_rank_cd(tokens, tsquery).desc(), KnowledgeChunk.id)
            .limit(CANDIDATE_K)
        ).all()
    scores, rows, ranks = {}, {}, {}
    for name, candidates in [("vector", vector_rows), ("keyword", keyword_rows)]:
        for rank, row in enumerate(candidates, start=1):
            chunk, _ = row
            rows[chunk.id] = row
            ranks.setdefault(chunk.id, {})[name] = rank
            scores[chunk.id] = scores.get(chunk.id, 0) + 1 / (RRF_OFFSET + rank)
    ranked_ids = sorted(scores, key=lambda cid: (-scores[cid], cid))[: query.top_k]
    return {
        "chunks": [
            {
                "evidence_id": cid,
                "document_id": rows[cid][1].id,
                "project_id": rows[cid][1].project_id,
                "source": rows[cid][1].source,
                "revision": rows[cid][1].revision,
                "content": rows[cid][0].content,
                "ranks": ranks[cid],
                "rrf_score": scores[cid],
                "retrieval_manifest": {
                    **rows[cid][0].manifest,
                    "strategy": strategy,
                    "top_k": query.top_k,
                    "candidate_k": CANDIDATE_K,
                    "rrf_offset": RRF_OFFSET,
                },
            }
            for cid in ranked_ids
        ]
    }
