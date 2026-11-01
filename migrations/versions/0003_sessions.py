"""Project-owned conversations and confirmed incident experience."""

import sqlalchemy as sa
from alembic import op

revision = "0003_sessions"
down_revision = "0002_knowledge"


def upgrade():
    op.create_table(
        "threads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("runs", sa.Column("thread_id", sa.String(36)))
    op.create_foreign_key("fk_runs_thread", "runs", "threads", ["thread_id"], ["id"])
    op.create_index("ix_runs_thread_started", "runs", ["thread_id", "started_at"])
    op.add_column("runs", sa.Column("source_run_id", sa.String(36)))
    op.create_foreign_key("fk_runs_source", "runs", "runs", ["source_run_id"], ["id"])
    op.add_column("runs", sa.Column("checkpoint_id", sa.String(100)))
    op.add_column("runs", sa.Column("interrupt_payload", sa.JSON))
    for column in [
        sa.Column("origin_run_id", sa.String(36)),
        sa.Column("service", sa.String(80)),
        sa.Column("start_time", sa.DateTime(timezone=True)),
        sa.Column("end_time", sa.DateTime(timezone=True)),
        sa.Column("applicability", sa.Text),
        sa.Column("content", sa.Text),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]:
        op.add_column("knowledge_documents", column)
    op.create_foreign_key(
        "fk_knowledge_origin", "knowledge_documents", "runs", ["origin_run_id"], ["id"]
    )
    op.create_unique_constraint("uq_knowledge_origin", "knowledge_documents", ["origin_run_id"])


def downgrade():
    op.drop_constraint("uq_knowledge_origin", "knowledge_documents", type_="unique")
    op.drop_constraint("fk_knowledge_origin", "knowledge_documents", type_="foreignkey")
    for name in [
        "created_at",
        "content",
        "applicability",
        "end_time",
        "start_time",
        "service",
        "origin_run_id",
    ]:
        op.drop_column("knowledge_documents", name)
    op.drop_column("runs", "interrupt_payload")
    op.drop_column("runs", "checkpoint_id")
    op.drop_constraint("fk_runs_source", "runs", type_="foreignkey")
    op.drop_column("runs", "source_run_id")
    op.drop_index("ix_runs_thread_started", table_name="runs")
    op.drop_constraint("fk_runs_thread", "runs", type_="foreignkey")
    op.drop_column("runs", "thread_id")
    op.drop_table("threads")
