"""Initial telemetry and investigation evidence tables."""

import sqlalchemy as sa
from alembic import op

revision = "0001_week1"
down_revision = None


def upgrade():
    op.create_table(
        "log_events",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("project_id", sa.String(50), nullable=False),
        sa.Column("service", sa.String(80), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", sa.String(10), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
    )
    op.create_index("ix_logs_scope_time", "log_events", ["project_id", "service", "timestamp"])
    op.create_table(
        "metric_points",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("project_id", sa.String(50), nullable=False),
        sa.Column("service", sa.String(80), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("unit", sa.String(30), nullable=False),
    )
    op.create_index(
        "ix_metrics_scope_time", "metric_points", ["project_id", "service", "timestamp"]
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("input", sa.Text, nullable=False),
        sa.Column("output", sa.JSON),
        sa.Column("versions", sa.JSON, nullable=False),
        sa.Column("usage", sa.JSON, nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "run_steps",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("input", sa.JSON, nullable=False),
        sa.Column("output", sa.JSON),
        sa.Column("error", sa.Text),
        sa.Column("duration_ms", sa.Float, nullable=False),
    )
    op.create_index("ix_steps_run_sequence", "run_steps", ["run_id", "sequence"], unique=True)


def downgrade():
    op.drop_table("run_steps")
    op.drop_table("runs")
    op.drop_table("metric_points")
    op.drop_table("log_events")
