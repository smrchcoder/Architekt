from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260612_0004"
down_revision = "20260612_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processing_runs",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_step", sa.String(length=64), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.String(length=36), nullable=True),
        sa.Column("section_1_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.article_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )


def downgrade() -> None:
    op.drop_table("processing_runs")
