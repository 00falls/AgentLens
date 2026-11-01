"""Vector indexing prerequisite, intentionally separate from conversation storage."""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0004_vectors"
down_revision = "0003_sessions"
branch_labels = ("vectors",)


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(120), primary_key=True),
        sa.Column(
            "document_id", sa.String(100), sa.ForeignKey("knowledge_documents.id"), nullable=False
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", Vector(512), nullable=False),
        sa.Column("manifest", sa.JSON, nullable=False),
    )


def downgrade():
    op.drop_table("knowledge_chunks")
