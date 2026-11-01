"""Import the one frozen historical reference into an empty CI database, never overwrite it."""

import hashlib
import json
from datetime import datetime

from agentlens.config import ROOT, Settings
from agentlens.db import Run, RunStep, Thread, create_session

SOURCE = "302c48a7-9420-4b60-9ee6-477f6da3e6f0"


def import_reference(path, data):
    source = data["run_id"]
    with create_session(Settings()) as session:
        if session.get(Run, source) is not None:
            print("Historical reference already exists; unchanged")
            return
        if data["thread_id"] and session.get(Thread, data["thread_id"]) is None:
            session.add(
                Thread(
                    id=data["thread_id"],
                    project_id=data["project_id"],
                    created_at=datetime.fromisoformat(data["started_at"]),
                )
            )
            session.flush()
        session.add(
            Run(
                id=source,
                thread_id=data["thread_id"],
                project_id=data["project_id"],
                execution_mode=data.get("execution_mode", "live"),
                status=data["status"],
                input=data["input"],
                output=data["output"],
                versions={
                    **data["versions"],
                    "historical_snapshot_import_sha256": hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest(),
                },
                usage=data["usage"],
                error=data["error"],
                started_at=datetime.fromisoformat(data["started_at"]),
                finished_at=datetime.fromisoformat(data["finished_at"]),
            )
        )
        session.flush()
        for s in data["steps"]:
            session.add(
                RunStep(
                    run_id=source,
                    sequence=s["sequence"],
                    kind=s["kind"],
                    name=s["name"],
                    input=s["input"],
                    output=s["output"],
                    error=s["error"],
                    duration_ms=s["duration_ms"],
                )
            )
        session.commit()
    print("Imported historical snapshot; no model or tool execution")


def main():
    path = ROOT / "reports/pgvector-acceptance.json"
    data = json.loads(path.read_text(encoding="utf-8"))["run"]
    assert data["run_id"] == SOURCE
    week7 = ROOT / "reports/week7-acceptance.json"
    archived = json.loads(week7.read_text(encoding="utf-8"))
    # Recover the old catalog from an already exported recording, not today's expanded MCP.
    catalog = archived["replay"]["versions"]["tool_catalog"]
    assert (
        hashlib.sha256(json.dumps(catalog, sort_keys=True).encode()).hexdigest()
        == (data["versions"]["tool_schemas_sha256"])
    )
    data["versions"]["tool_catalog"] = catalog
    import_reference(path, data)
    import_reference(week7, archived["frozen"])


if __name__ == "__main__":
    main()
