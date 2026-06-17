"""remove knowledge_model_json column from processing_runs."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260617_0010"
down_revision = "20260617_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("processing_runs", "knowledge_model_json")


def downgrade() -> None:
    op.add_column(
        "processing_runs",
        sa.Column("knowledge_model_json", sa.JSON(), nullable=True),
    )
