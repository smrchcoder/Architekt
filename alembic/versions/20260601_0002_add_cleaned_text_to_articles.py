from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260601_0002"
down_revision = "20260531_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("cleaned_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("articles", "cleaned_text")

