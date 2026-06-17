"""add knowledge_model_json column to processing_runs."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260617_0009"
down_revision = "2fa022c93fe4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "processing_runs",
        sa.Column("knowledge_model_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("processing_runs", "knowledge_model_json")
