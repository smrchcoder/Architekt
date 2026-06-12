from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.ingestion.schema.article_schema import ArticleCreate
from app.modules.ingestion.services.raw_text_ingestion_service import (
    RawTextIngestionService,
)
from app.modules.ingestion.services.url_ingestion_service import UrlIngestionService
from app.storage.models import Article


class IngestionService:
    """Border-level entry point selecting raw-text vs URL ingestion."""

    def __init__(self) -> None:
        self._raw = RawTextIngestionService()
        self._url = UrlIngestionService()

    def ingest_article(self, db: Session, payload: ArticleCreate) -> Article:
        if payload.raw_text is not None:
            return self._raw.ingest(db, payload)
        return self._url.ingest(db, payload)
