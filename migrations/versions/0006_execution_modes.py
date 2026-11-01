"""Immutable recordings, frozen tool data and explicit execution provenance."""

import sqlalchemy as sa
from alembic import op

revision = "0006_execution_modes"
down_revision = "0005_observability"


def upgrade():
    op.create_table(
        "recordings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(50), nullable=False),
        sa.Column("source_run_id", sa.String(36), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_recordings_project_id", "recordings", ["project_id"])
    op.create_table(
        "frozen_scenarios",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(50), nullable=False),
        sa.Column("source_run_id", sa.String(36), sa.ForeignKey("runs.id")),
        sa.Column("schema_name", sa.String(63), unique=True, nullable=False),
        sa.Column("manifest", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_frozen_scenarios_project_id", "frozen_scenarios", ["project_id"])
    op.add_column(
        "runs", sa.Column("execution_mode", sa.String(20), nullable=False, server_default="live")
    )
    op.add_column("runs", sa.Column("recording_id", sa.String(36), sa.ForeignKey("recordings.id")))
    op.add_column(
        "runs", sa.Column("scenario_id", sa.String(36), sa.ForeignKey("frozen_scenarios.id"))
    )
    op.add_column("runs", sa.Column("failure_detail", sa.JSON))
    op.add_column("run_steps", sa.Column("source_step_sequence", sa.Integer))


def downgrade():
    op.drop_column("run_steps", "source_step_sequence")
    for column in ["failure_detail", "scenario_id", "recording_id", "execution_mode"]:
        op.drop_column("runs", column)
    op.drop_table("frozen_scenarios")
    op.drop_table("recordings")
