from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.ingestion.schema.article_schema import ArticleCreate
from app.modules.ingestion.services.document_cleaning_service import (
    DocumentCleaningService,
)
from app.storage.models import Article
from app.storage.repository import ArticleRepository


class RawTextIngestionService:
    def __init__(
        self,
        repo: ArticleRepository | None = None,
        cleaner: DocumentCleaningService | None = None,
    ) -> None:
        self.repo = repo or ArticleRepository()
        self.cleaner = cleaner or DocumentCleaningService()

    def ingest(self, db: Session, payload: ArticleCreate) -> Article:
        raw_text = payload.raw_text or ""
        cleaned_text = self.cleaner.clean(raw_text)
        word_count = len(cleaned_text.split())
        article = Article(
            source_url=None,
            raw_text=raw_text or None,
            cleaned_text=cleaned_text or None,
            word_count=word_count,
            processing_time=None,
            source_title=payload.source_title,
            source_domain=payload.source_domain,
        )
        return self.repo.create(db, article)
