"""add section result columns to processing_runs."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260612_0006"
down_revision = "20260612_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "processing_runs",
        sa.Column("section_2_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "processing_runs",
        sa.Column("section_3_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "processing_runs",
        sa.Column("section_4_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "processing_runs",
        sa.Column("section_5_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "processing_runs",
        sa.Column("section_6_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("processing_runs", "section_6_json")
    op.drop_column("processing_runs", "section_5_json")
    op.drop_column("processing_runs", "section_4_json")
    op.drop_column("processing_runs", "section_3_json")
    op.drop_column("processing_runs", "section_2_json")
