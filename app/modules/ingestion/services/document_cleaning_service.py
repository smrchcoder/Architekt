from __future__ import annotations

import re
from html import unescape


class DocumentCleaningService:
    """Normalize fetched or pasted content into extraction-ready plain text."""

    _boilerplate_patterns = (
        r"^Table of contents$",
        r"^Subscribe to.*$",
        r"^Sign up for.*$",
        r"^Share this post.*$",
        r"^Related articles?.*$",
        r"^Recommended for you.*$",
        r"^Cookie (policy|settings).*$",
        r"^All rights reserved\.?$",
    )

    def clean(self, raw_text: str | None) -> str:
        text = unescape(raw_text or "")
        text = self._strip_html_tags(text)
        lines = [self._normalize_line(line) for line in text.splitlines()]
        lines = [line for line in lines if line and not self._is_boilerplate(line)]
        return "\n".join(lines).strip()

    def _strip_html_tags(self, text: str) -> str:
        without_script = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
        without_tags = re.sub(r"(?s)<[^>]+>", " ", without_script)
        return without_tags

    def _normalize_line(self, line: str) -> str:
        normalized = re.sub(r"\s+", " ", line).strip()
        return normalized

    def _is_boilerplate(self, line: str) -> bool:
        return any(re.match(pattern, line, re.IGNORECASE) for pattern in self._boilerplate_patterns)

