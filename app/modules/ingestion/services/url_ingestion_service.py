from __future__ import annotations

from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.modules.ingestion.firecrawl_client import FirecrawlClient
from app.modules.ingestion.schema.article_schema import ArticleCreate
from app.modules.ingestion.services.document_cleaning_service import DocumentCleaningService
from app.storage.models import Article
from app.storage.repository import ArticleRepository


class UrlIngestionService:
    def __init__(
        self,
        repo: ArticleRepository | None = None,
        firecrawl: FirecrawlClient | None = None,
        cleaner: DocumentCleaningService | None = None,
    ) -> None:
        self.repo = repo or ArticleRepository()
        self.firecrawl = firecrawl or FirecrawlClient()
        self.cleaner = cleaner or DocumentCleaningService()

    def ingest(self, db: Session, payload: ArticleCreate) -> Article:
        if not payload.source_url:
            raise ValueError("source_url is required for URL ingestion")

        source_url = str(payload.source_url)
        existing = self.repo.get_by_source_url(db, source_url)
        if existing is not None:
            return existing

        scrape = self.firecrawl.scrape_url_as_markdown(source_url)

        raw_text = scrape.markdown
        cleaned_text = self.cleaner.clean(raw_text)
        word_count = len(cleaned_text.split())

        source_domain = payload.source_domain
        if not source_domain:
            host = urlparse(source_url).netloc.lower()
            source_domain = host[4:] if host.startswith("www.") else host

        article = Article(
            source_url=source_url,
            raw_text=raw_text,
            cleaned_text=cleaned_text or None,
            word_count=word_count,
            processing_time=scrape.elapsed_ms,
            source_title=payload.source_title,
            source_domain=source_domain,
        )
        return self.repo.create(db, article)
