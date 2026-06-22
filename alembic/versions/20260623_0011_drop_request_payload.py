"""drop request_payload column from processing_runs."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260623_0011"
down_revision = "20260617_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("processing_runs", "request_payload")


def downgrade() -> None:
    op.add_column(
        "processing_runs",
        sa.Column("request_payload", sa.JSON(), nullable=True),
    )
