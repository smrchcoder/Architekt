from __future__ import annotations

import re
from html import unescape


class DocumentCleaningService:
    """Aggressively clean markdown text to retain only the article body.

    Designed to run AFTER Firecrawl's only_main_content=True extraction, so
    we assume the input is already mostly article content. This removes
    remaining boilerplate, navigation cruft, cookie notices, author bios,
    and other noise that Firecrawl's main-content detection may not catch.

    Strategy:
      1. Unescape HTML entities.
      2. Strip any remaining HTML/XML tags.
      3. Remove boilerplate sections by heading match (nav, footer, sidebar patterns).
      4. Remove boilerplate paragraphs/lines matching known patterns.
      5. Collapse excessive blank lines and whitespace.
    """

    _boilerplate_exact_headings = (
        r"^(?:#+\s*)?"
        r"(?:"
        r"Table\s+of\s+Contents|Contents|Navigation|"
        r"Subscribe|Sign\s+Up|"
        r"Share\s+(?:this|the)\s+(?:post|article)|"
        r"Related\s+(?:Articles?|Posts?|Stories?|Reading)|"
        r"Recommended(?:\s+(?:for|Reading))?|"
        r"You\s+(?:May|Might)\s+(?:Also\s+)?(?:Like|Enjoy|Be\s+Interested)|"
        r"About\s+(?:the\s+)?(?:Author|Me|Us|Team|Writer|Contributor)|"
        r"Author\s+(?:Bio|Information|Details|Profile)|"
        r"Cookie\s+(?:Policy|Settings|Notice|Consent)|"
        r"We\s+(?:Use|Value|Respect)\s+(?:Cookies|Your\s+Privacy)|"
        r"Privacy\s+(?:Policy|Notice|Statement|Overview)|"
        r"Terms\s+(?:of\s+(?:Use|Service)|and\s+Conditions)|"
        r"Advertisement|Sponsored|Promoted|"
        r"Follow\s+(?:Us|Me|The\s+Author)|"
        r"Connect(?:\s+(?:with|Us))?|"
        r"Comments?|Discussion|Feedback|"
        r"Also\s+(?:on|from|in)|"
        r"More\s+(?:from|in|on|by|Articles?|Posts?|Stories?|Reading)"
        r")"
        r"(?:\s*:\s*)?\s*$"
    )

    _boilerplate_prefix_headings = (
        r"^(?:#+\s*)?"
        r"(?:"
        r"Subscribe(?:\s+(?:to|for)\s+\S)|"
        r"Sign\s+Up(?:\s+for\s+\S)|"
        r"Follow\s+(?:Us|Me|The\s+Author)\s+on\s+\S|"
        r"Connect\s+with\s+\S|"
        r"More\s+(?:from|in|on|by)\s+\S|"
        r"Also\s+(?:on|from|in)\s+\S|"
        r"About\s+(?:the\s+)?Author\s+\S|"
        r"Share\s+(?:this|the)\s+(?:post|article)\s+on\s+\S|"
        r"Comments?\s+(?:on|from|by)"
        r")"
    )

    _boilerplate_line_patterns = (
        r"^Table of contents$",
        r"^Contents$",
        r"^Subscribe to.*$",
        r"^Sign up for.*$",
        r"^Share this (?:post|article).*$",
        r"^Related articles?\.?$",
        r"^Recommended for you\.?$",
        r"^Cookie (?:policy|settings|notice|consent).*$",
        r"^All rights reserved\.?$",
        r"^Copyright(?: \d{4}| ©).*$",
        r"^Published (?:on|at|in) .*$",
        r"^Originally published .*$",
        r"^This (?:post|article) (?:was|is) (?:originally |first )?published .*$",
        r"^Written by .*$",
        r"^By .*$",
        r"^Photo (?:by|credit|courtesy).*$",
        r"^Image (?:credit|source|courtesy).*$",
        r"^Last updated (?:on )?.*$",
        r"^(?:Click|Tap|Read more|Learn more|Find out more).*$",
        r"^Back to (?:top|blog|home|main).*$",
        r"^↑ Back to top$",
        r"^(?:Follow|Find) (?:us|me) on .*$",
        r"^\[.*?\](?:\(.*?\))?\s*$",
    )

    _cookie_consent_indicators = (
        r"(?:we|this\s+(?:site|website))\s+(?:use|utilise|employ)\s+cookies",
        r"cookie\s+(?:policy|notice|consent|settings|preferences)",
        r"(?:accept|reject|manage)\s+(?:all\s+)?cookies",
        r"by\s+(?:continuing|using|visiting).*you\s+(?:agree|consent|accept)",
    )

    def clean(self, raw_text: str | None) -> str:
        if not raw_text:
            return ""

        text = unescape(raw_text)
        text = self._strip_remaining_html(text)
        text = self._remove_cookie_consent_paragraphs(text)
        text = self._strip_boilerplate_sections(text)
        text = self._strip_boilerplate_lines(text)
        text = self._normalize_whitespace(text)
        return text.strip()

    def _strip_remaining_html(self, text: str) -> str:
        without_script = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", text)
        without_tags = re.sub(r"(?s)<[^>]+>", " ", without_script)
        without_comments = re.sub(r"(?s)<!--.*?-->", " ", without_tags)
        return without_comments

    def _remove_cookie_consent_paragraphs(self, text: str) -> str:
        pattern = "|".join(f"(?:{ind})" for ind in self._cookie_consent_indicators)
        cookie_re = re.compile(pattern, re.IGNORECASE)
        lines = text.splitlines()
        filtered: list[str] = []
        skip_count = 0
        for line in lines:
            stripped = line.strip()
            if skip_count > 0:
                skip_count -= 1
                if not stripped:
                    skip_count = 0
                continue
            if cookie_re.search(stripped):
                paragraphs = stripped.split(". ")
                cleaned_parts = [
                    p
                    for p in paragraphs
                    if not cookie_re.search(p)
                ]
                if cleaned_parts:
                    filtered.append(". ".join(cleaned_parts))
                else:
                    skip_count = 3
                continue
            filtered.append(line)
        return "\n".join(filtered)

    def _strip_boilerplate_sections(self, text: str) -> str:
        """Remove entire sections whose heading matches boilerplate patterns.

        A section starts at a matching heading and ends at the next heading of
        equal or higher level, or end of text.
        """
        exact_re = re.compile(self._boilerplate_exact_headings, re.IGNORECASE)
        prefix_re = re.compile(self._boilerplate_prefix_headings, re.IGNORECASE)
        lines = text.splitlines()
        result: list[str] = []
        skipping = False
        skip_level = 0

        for line in lines:
            stripped = line.strip()
            is_heading = bool(stripped.startswith("#"))
            heading_level = 0
            if is_heading:
                match = re.match(r"^(#+)\s", stripped)
                if match:
                    heading_level = len(match.group(1))

            is_boilerplate_heading = is_heading and (
                exact_re.match(stripped) or prefix_re.match(stripped)
            )

            if is_boilerplate_heading:
                skipping = True
                skip_level = heading_level
                continue

            if skipping:
                if is_heading and heading_level > 0 and heading_level <= skip_level:
                    skipping = False
                else:
                    continue

            result.append(line)

        return "\n".join(result)

    def _strip_boilerplate_lines(self, text: str) -> str:
        combined = "|".join(self._boilerplate_line_patterns)
        line_re = re.compile(combined, re.IGNORECASE)
        lines = []
        for line in text.splitlines():
            if line_re.match(line.strip()):
                continue
            lines.append(line)
        return "\n".join(lines)

    def _normalize_whitespace(self, text: str) -> str:
        lines = text.splitlines()
        normalized = []
        blank_streak = 0
        for line in lines:
            norm = re.sub(r"[ \t]+", " ", line)
            if norm.strip():
                normalized.append(norm)
                blank_streak = 0
            else:
                blank_streak += 1
                if blank_streak <= 2:
                    normalized.append("")
        return "\n".join(normalized)
