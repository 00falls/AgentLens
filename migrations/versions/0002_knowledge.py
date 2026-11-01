"""Knowledge metadata, independent of the optional vector extension.

The previous week-3 migration was never applied. Its vector table is now in 0004_vectors,
so confirmed experience and checkpoints can be tested on the existing PostgreSQL server.
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_knowledge"
down_revision = "0001_week1"


def upgrade():
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("project_id", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("revision", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
    )
    op.create_index("ix_knowledge_documents_project_id", "knowledge_documents", ["project_id"])


def downgrade():
    op.drop_table("knowledge_documents")
