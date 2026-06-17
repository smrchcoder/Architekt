from __future__ import annotations

from time import perf_counter

from app.core.config import settings
from app.modules.ingestion.schema.firecrawl_client_schema import (
    FirecrawlMediaItem,
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
        started = perf_counter()
        from firecrawl import Firecrawl

        fc = Firecrawl(api_key=self.api_key)
        doc = fc.scrape(
            url,
            formats=formats or ["markdown"],
            only_main_content=True,
            remove_base64_images=True,
            block_ads=True,
        )

        elapsed_ms = int((perf_counter() - started) * 1000)
        markdown = getattr(doc, "markdown", None)
        if not markdown:
            markdown = doc.get("markdown") if isinstance(doc, dict) else None
        if not markdown:
            raise ValueError("Firecrawl scrape succeeded but markdown was empty")

        source_title = None
        source_description = None
        language = None
        metadata = getattr(doc, "metadata", None)
        if metadata is not None:
            source_title = getattr(metadata, "title", None)
            source_description = getattr(metadata, "description", None)
            language = getattr(metadata, "language", None)

        media_items = self._collect_media(doc)
        extraction_warnings = self._collect_warnings(doc)

        return FirecrawlScrapeResult(
            url=url,
            markdown=markdown,
            elapsed_ms=elapsed_ms,
            source_title=source_title,
            source_description=source_description,
            language=language,
            media_items=media_items,
            extraction_warnings=extraction_warnings,
        )

    def _collect_media(self, doc) -> list[FirecrawlMediaItem]:
        items: list[FirecrawlMediaItem] = []

        images = getattr(doc, "images", None)
        if isinstance(images, list):
            for img_url in images:
                items.append(
                    FirecrawlMediaItem(
                        media_type="image",
                        url=str(img_url),
                        alt_text=None,
                    )
                )

        audio = getattr(doc, "audio", None)
        if audio:
            items.append(
                FirecrawlMediaItem(
                    media_type="audio",
                    url=str(audio),
                    alt_text=None,
                )
            )

        video = getattr(doc, "video", None)
        if video:
            items.append(
                FirecrawlMediaItem(
                    media_type="video",
                    url=str(video),
                    alt_text=None,
                )
            )

        return items

    @staticmethod
    def _collect_warnings(doc) -> list[str]:
        warnings: list[str] = []
        warning = getattr(doc, "warning", None)
        if warning:
            warnings.append(str(warning))

        metadata = getattr(doc, "metadata", None)
        if metadata:
            error = getattr(metadata, "error", None)
            if error:
                warnings.append(str(error))

        return warnings
