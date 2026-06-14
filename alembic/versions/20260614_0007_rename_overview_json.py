from __future__ import annotations

from alembic import op

revision = "20260614_0007"
down_revision = "20260612_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("processing_runs", "overview_json", new_column_name="section_1_json")


def downgrade() -> None:
    op.alter_column("processing_runs", "section_1_json", new_column_name="overview_json")
