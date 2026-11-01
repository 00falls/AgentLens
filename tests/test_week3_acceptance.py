"""One real business case; skip explicitly when the agreed pgvector prerequisite is absent."""

import json
import os

import httpx
import pytest
from sqlalchemy import text

from agentlens.config import ROOT, Settings
from agentlens.db import create_session
from agentlens.evaluation import evaluate, load_cases


def test_pool_exhaustion_with_runbook_citations():
    settings = Settings()
    with create_session(settings) as session:
        vector = session.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
        if vector is None:
            pytest.skip("pgvector is absent; user chose to retain the existing environment")
        chunks = session.scalar(text("SELECT count(*) FROM knowledge_chunks"))
        assert chunks == 36, "Import the 18 runbooks before the real-model acceptance"
    assert (settings.embedding_path / "artifacts.json").is_file(), "Download pinned BGE first"
    case = load_cases(ROOT / "datasets/week3.jsonl")[0]
    events = []
    with httpx.Client(
        base_url=os.environ.get("AGENTLENS_ACCEPTANCE_URL", "http://127.0.0.1:8000"),
        timeout=120,
        headers={"X-AgentLens-Project": case["project_id"]},
    ) as client:
        with client.stream(
            "POST",
            "/agent/stream",
            json={"project_id": case["project_id"], "prompt": case["input"]},
        ) as response:
            assert response.status_code == 200
            for line in response.iter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
        assert events[-1]["event"] == "run_finished", events[-1]
        run = client.get(f"/runs/{events[-1]['run_id']}").json()
    verdict = evaluate(case, run)
    target = ROOT / "reports/week3-acceptance.json"
    target.write_text(
        json.dumps(
            {
                "status": "complete",
                "case_id": case["case_id"],
                "real_model": True,
                "evaluation": verdict,
                "run": run,
                "events": events,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    assert verdict["passed"], verdict
    assert run["versions"]["retrieval"]["strategy"] == "vector"
    assert any(event["event"] == "answer_delta" for event in events)
