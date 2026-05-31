from __future__ import annotations

from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.modules.ingestion.schemas import ArticleCreate
from app.storage.models import Article
from app.storage.repository import ArticleRepository


class IngestionService:
    def __init__(self, repo: ArticleRepository | None = None) -> None:
        self.repo = repo or ArticleRepository()

    def ingest_article(self, db: Session, payload: ArticleCreate) -> Article:
        raw_text = payload.raw_text
        word_count = len(raw_text.split()) if raw_text else 0
        source_url = str(payload.source_url) if payload.source_url else None
        source_domain = payload.source_domain
        if not source_domain and source_url:
            host = urlparse(source_url).netloc.lower()
            source_domain = host[4:] if host.startswith("www.") else host

        article = Article(
            source_url=source_url,
            raw_text=raw_text,
            word_count=word_count,
            processing_time=None,
            source_title=payload.source_title,
            source_domain=source_domain,
        )
        return self.repo.create(db, article)

