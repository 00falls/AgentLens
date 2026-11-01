"""Project scoped identity and execution audit trail."""

import sqlalchemy as sa
from alembic import op

revision = "0007_audit"
down_revision = "0006_execution_modes"


def upgrade():
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(50), nullable=True),
        sa.Column("actor", sa.String(80), nullable=False),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("resource", sa.String(240), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("result", sa.String(60), nullable=False),
        sa.Column("detail", sa.JSON, nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_scope_time", "audit_events", ["project_id", "timestamp"])


def downgrade():
    op.drop_table("audit_events")
