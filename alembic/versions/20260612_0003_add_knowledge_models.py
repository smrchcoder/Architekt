from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260612_0003"
down_revision = "20260601_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "knowledge_models" in inspector.get_table_names():
        op.drop_table("knowledge_models")

    article_columns = {column["name"] for column in inspector.get_columns("articles")}
    if "unique_id" in article_columns and "article_id" not in article_columns:
        with op.batch_alter_table("articles") as batch_op:
            batch_op.alter_column("unique_id", new_column_name="article_id")

    op.create_table(
        "knowledge_models",
        sa.Column("article_id", sa.String(length=36), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("raw_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.article_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("article_id"),
    )


def downgrade() -> None:
    op.drop_table("knowledge_models")

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    article_columns = {column["name"] for column in inspector.get_columns("articles")}
    if "article_id" in article_columns and "unique_id" not in article_columns:
        with op.batch_alter_table("articles") as batch_op:
            batch_op.alter_column("article_id", new_column_name="unique_id")
