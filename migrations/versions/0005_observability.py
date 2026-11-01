"""Run/span correlation and append-only OTLP span storage, independent of pgvector."""

import sqlalchemy as sa
from alembic import op

revision = "0005_observability"
down_revision = "0003_sessions"
branch_labels = ("platform",)


def upgrade():
    for name, length in [("trace_id", 32), ("span_id", 16), ("request_span_id", 16)]:
        op.add_column("runs", sa.Column(name, sa.String(length)))
    op.create_index("ix_runs_trace_id", "runs", ["trace_id"])
    op.add_column("run_steps", sa.Column("span_id", sa.String(16)))
    op.create_table(
        "trace_spans",
        sa.Column("trace_id", sa.String(32), primary_key=True),
        sa.Column("span_id", sa.String(16), primary_key=True),
        sa.Column("parent_span_id", sa.String(16)),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("start_ns", sa.BigInteger, nullable=False),
        sa.Column("end_ns", sa.BigInteger, nullable=False),
        sa.Column("attributes", sa.JSON, nullable=False),
        sa.Column("resource", sa.JSON, nullable=False),
        sa.Column("scope", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("events", sa.JSON, nullable=False),
    )


def downgrade():
    op.drop_table("trace_spans")
    op.drop_column("run_steps", "span_id")
    op.drop_index("ix_runs_trace_id", table_name="runs")
    for name in ["request_span_id", "span_id", "trace_id"]:
        op.drop_column("runs", name)
