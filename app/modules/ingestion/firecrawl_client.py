from __future__ import annotations

from time import perf_counter

from app.core.config import settings
from app.modules.ingestion.schema.firecrawl_client_schema import (
    FirecrawlScrapeRequest,
    FirecrawlScrapeResult,
)


class FirecrawlClient:
    def __init__(self) -> None:
        self.api_key = settings.firecrawl_api_key or ""

    def scrape_url_as_markdown(self, url: str) -> FirecrawlScrapeResult:
        if not self.api_key:
            raise ValueError("FIRECRAWL_API_KEY is not set")

        formats = [
            fmt.strip()
            for fmt in (settings.firecrawl_formats or "markdown").split(",")
            if fmt.strip()
        ]
        request = FirecrawlScrapeRequest(url=url, formats=formats or ["markdown"])
        started = perf_counter()
        from firecrawl import Firecrawl

        fc = Firecrawl(api_key=self.api_key)
        doc = fc.scrape(request.url, formats=request.formats)

        elapsed_ms = int((perf_counter() - started) * 1000)
        markdown = getattr(doc, "markdown", None)
        if not markdown:
            markdown = doc.get("markdown") if isinstance(doc, dict) else None
        if not markdown:
            raise ValueError("Firecrawl scrape succeeded but markdown was empty")
        return FirecrawlScrapeResult(url=request.url, markdown=markdown, elapsed_ms=elapsed_ms)
