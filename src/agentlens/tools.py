from sqlalchemy import select
from sqlalchemy.orm import Session

from agentlens.db import LogEvent, MetricPoint
from agentlens.schemas import LogQuery, MetricQuery


def search_logs(session: Session, project_id: str, query: LogQuery) -> dict:
    statement = select(LogEvent).where(
        LogEvent.project_id == project_id,
        LogEvent.service == query.service,
        LogEvent.timestamp >= query.start_time,
        LogEvent.timestamp < query.end_time,
    )
    if query.level is not None:
        statement = statement.where(LogEvent.level == query.level)
    rows = session.scalars(
        statement.order_by(LogEvent.timestamp, LogEvent.id).limit(query.limit)
    ).all()
    return {
        "logs": [
            {
                "evidence_id": row.id,
                "timestamp": row.timestamp.isoformat(),
                "service": row.service,
                "level": row.level,
                "message": row.message,
            }
            for row in rows
        ]
    }


def query_metrics(session: Session, project_id: str, query: MetricQuery) -> dict:
    statement = select(MetricPoint).where(
        MetricPoint.project_id == project_id,
        MetricPoint.service == query.service,
        MetricPoint.timestamp >= query.start_time,
        MetricPoint.timestamp < query.end_time,
    )
    if query.metric_name is not None:
        statement = statement.where(MetricPoint.name == query.metric_name)
    rows = session.scalars(
        statement.order_by(MetricPoint.timestamp, MetricPoint.id).limit(query.limit)
    ).all()
    return {
        "metrics": [
            {
                "evidence_id": row.id,
                "timestamp": row.timestamp.isoformat(),
                "service": row.service,
                "name": row.name,
                "value": row.value,
                "unit": row.unit,
            }
            for row in rows
        ]
    }
