"""add media_items and extraction_warnings columns to articles."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260615_0008"
down_revision = "20260614_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("media_items", sa.JSON(), nullable=True),
    )
    op.add_column(
        "articles",
        sa.Column("extraction_warnings", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("articles", "extraction_warnings")
    op.drop_column("articles", "media_items")
