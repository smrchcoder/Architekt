from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260531_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "articles",
        sa.Column("unique_id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processing_time", sa.Integer(), nullable=True),
        sa.Column("source_title", sa.String(length=512), nullable=True),
        sa.Column("source_domain", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("articles")

