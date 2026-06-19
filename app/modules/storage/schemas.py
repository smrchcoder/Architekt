from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ConvertedArticleRead(BaseModel):
    article_id: str
    source_title: str | None
    source_domain: str | None
    source_url: str | None
    word_count: int
    created_at: datetime
    run_id: str
    status: str
    updated_at: datetime
    sections: dict[str, Any | None]
