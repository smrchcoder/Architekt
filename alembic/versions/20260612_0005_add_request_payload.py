"""add request_payload column to processing_runs."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260612_0005"
down_revision = "20260612_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "processing_runs",
        sa.Column("request_payload", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("processing_runs", "request_payload")
