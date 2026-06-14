"""Migration 0004 already creates the column as section_1_json — no rename needed."""

from __future__ import annotations


revision = "20260614_0007"
down_revision = "20260612_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
