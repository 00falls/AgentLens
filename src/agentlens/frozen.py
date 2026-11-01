"""Freeze real PostgreSQL tables, including vectors, in a separate immutable app namespace."""

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from agentlens.config import ROOT, Settings
from agentlens.conversations import ConversationError
from agentlens.db import FrozenScenario, Run, create_session, database_engine
from agentlens.evaluation import load_cases
from agentlens.replay import digest

TABLES = ["log_events", "metric_points", "knowledge_documents", "knowledge_chunks"]


def table_manifest(connection, schema: str) -> dict:
    quoted = connection.dialect.identifier_preparer.quote_schema(schema)
    result = {}
    for table in TABLES:
        rows = list(
            connection.scalars(
                text(f"SELECT row_to_json(t)::text FROM {quoted}.{table} t ORDER BY id")
            )
        )
        result[table] = {
            "rows": len(rows),
            "sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest(),
        }
    return result


def read_scenario(session, scenario_id: str, project: str) -> dict:
    row = session.scalar(
        select(FrozenScenario).where(
            FrozenScenario.id == scenario_id, FrozenScenario.project_id == project
        )
    )
    if row is None:
        raise ConversationError(404, "Frozen scenario not found")
    return {
        "scenario_id": row.id,
        "project_id": row.project_id,
        "source_run_id": row.source_run_id,
        "schema_name": row.schema_name,
        "manifest": row.manifest,
        "created_at": row.created_at.isoformat(),
    }


def freeze_scenario(
    settings: Settings, case_id: str, project: str, source_run_id: str | None = None
) -> dict:
    case = next(
        (
            c
            for c in load_cases(ROOT / "datasets/week6/dev.jsonl")
            if c["case_id"] == case_id and c["project_id"] == project
        ),
        None,
    )
    if case is None:
        raise ConversationError(404, "Development case not found")
    scenario_id = str(uuid4())
    schema = "frozen_" + scenario_id.replace("-", "")
    engine = database_engine(settings.database_url.get_secret_value())
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with connection.begin():
            if source_run_id is not None:
                source = connection.execute(
                    select(Run.project_id, Run.input).where(Run.id == source_run_id)
                ).first()
                if source is None or source.project_id != project:
                    raise ConversationError(404, "Source run not found")
                if source.input != case["input"]:
                    raise ConversationError(409, "Source run does not match this frozen case")
            connection.execute(text(f"CREATE SCHEMA {schema}"))
            for table in TABLES:
                query = (
                    f"SELECT t.* FROM public.{table} t WHERE project_id=:project"
                    if table != "knowledge_chunks"
                    else "SELECT t.* FROM public.knowledge_chunks t "
                    "JOIN public.knowledge_documents d ON d.id=t.document_id "
                    "WHERE d.project_id=:project"
                )
                connection.execute(
                    text(f"CREATE TABLE {schema}.{table} AS {query}"), {"project": project}
                )
            manifest = {
                "format_version": 1,
                "case": case,
                "tables": table_manifest(connection, schema),
                "embedding_artifacts_sha256": hashlib.sha256(
                    (settings.embedding_path / "artifacts.json").read_bytes()
                ).hexdigest(),
                "dataset_sha256": hashlib.sha256(
                    (ROOT / "datasets/week6/dev.jsonl").read_bytes()
                ).hexdigest(),
            }
            manifest["sha256"] = digest(manifest)
            connection.execute(
                FrozenScenario.__table__.insert().values(
                    id=scenario_id,
                    project_id=project,
                    source_run_id=source_run_id,
                    schema_name=schema,
                    manifest=manifest,
                    created_at=datetime.now(UTC),
                )
            )
    with create_session(settings) as session:
        return read_scenario(session, scenario_id, project)


def verify_scenario(settings: Settings, scenario: dict):
    manifest = scenario["manifest"]
    expected = {k: v for k, v in manifest.items() if k != "sha256"}
    if digest(expected) != manifest["sha256"]:
        raise ConversationError(409, "Frozen scenario manifest integrity check failed")
    engine = database_engine(settings.database_url.get_secret_value())
    with engine.connect() as connection:
        if table_manifest(connection, scenario["schema_name"]) != manifest["tables"]:
            raise ConversationError(409, "Frozen scenario data changed")
    if (
        hashlib.sha256((settings.embedding_path / "artifacts.json").read_bytes()).hexdigest()
        != (manifest["embedding_artifacts_sha256"])
    ):
        raise ConversationError(409, "Query embedding artifacts differ from frozen scenario")


def tool_session(settings: Settings, project: str, scenario_id: str | None) -> Session:
    if scenario_id is None:
        return create_session(settings)
    with create_session(settings) as registry:
        scenario = read_scenario(registry, scenario_id, project)
    engine = database_engine(settings.database_url.get_secret_value())
    return Session(
        engine.execution_options(schema_translate_map={None: scenario["schema_name"]}),
        expire_on_commit=False,
    )


def list_scenarios(session, project: str) -> list[dict]:
    return [
        {
            "scenario_id": r.id,
            "source_run_id": r.source_run_id,
            "case_id": r.manifest["case"]["case_id"],
            "sha256": r.manifest["sha256"],
            "created_at": r.created_at.isoformat(),
        }
        for r in session.scalars(
            select(FrozenScenario)
            .where(FrozenScenario.project_id == project)
            .order_by(FrozenScenario.created_at.desc())
        )
    ]
