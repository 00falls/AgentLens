import json
from datetime import datetime

from sqlalchemy.orm import Session

from agentlens.config import ROOT
from agentlens.db import LogEvent, MetricPoint


def seed(session: Session, dataset=ROOT / "datasets/telemetry.json") -> dict:
    data = json.loads(dataset.read_text(encoding="utf-8"))
    for collection, model in [("logs", LogEvent), ("metrics", MetricPoint)]:
        for item in data[collection]:
            session.merge(model(**{**item, "timestamp": datetime.fromisoformat(item["timestamp"])}))
    session.commit()
    return {"logs": len(data["logs"]), "metrics": len(data["metrics"]), "synthetic": True}
