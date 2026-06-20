from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.modules.storage.schemas import ConvertedArticleRead
from app.storage.db import get_db
from app.storage.repository import ArticleRepository


router = APIRouter(prefix="/storage", tags=["storage"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/articles/converted", response_model=list[ConvertedArticleRead])
def get_converted_articles(db: Session = Depends(get_db)):
    """Fetch all articles that have been fully processed into sections."""
    repo = ArticleRepository()
    rows = repo.get_converted(db)
    return [
        ConvertedArticleRead(
            article_id=article.article_id,
            source_title=article.source_title,
            source_domain=article.source_domain,
            source_url=article.source_url,
            word_count=article.word_count,
            created_at=article.created_at,
            run_id=run.run_id,
            status=run.status,
            updated_at=run.updated_at,
            sections={
                "overview": run.section_1_json,
                "key_concepts": run.section_2_json,
                "problem_statement": run.section_3_json,
                "architecture": run.section_4_json,
                "flow": run.section_5_json,
                "tradeoffs": run.section_6_json,
            },
        )
        for article, run in rows
    ]
