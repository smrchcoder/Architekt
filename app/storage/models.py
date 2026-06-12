from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.db import Base


class Article(Base):
    __tablename__ = "articles"

    article_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    cleaned_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processing_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_domain: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class KnowledgeModelRecord(Base):
    __tablename__ = "knowledge_models"

    article_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("articles.article_id", ondelete="CASCADE"),
        primary_key=True,
    )
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
