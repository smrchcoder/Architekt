from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.modules.storage.schemas import ConvertedArticleRead
from app.storage.db import get_db
from app.storage.repository import ArticleRepository


router = APIRouter(prefix="/storage", tags=["storage"])


def _to_converted_article_read(article, run) -> ConvertedArticleRead:
    return ConvertedArticleRead(
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


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/health/db")
def database_health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        ) from exc
    return {"status": "ok", "database": "ok"}


@router.get("/articles/converted", response_model=list[ConvertedArticleRead])
def get_converted_articles(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Fetch all articles that have been fully processed into sections."""
    repo = ArticleRepository()
    rows = repo.get_converted(db, limit=limit, offset=offset)
    return [_to_converted_article_read(article, run) for article, run in rows]


@router.get(
    "/articles/converted/by-run/{run_id}", response_model=ConvertedArticleRead
)
def get_converted_article_by_run_id(
    run_id: str,
    db: Session = Depends(get_db),
):
    """Fetch the converted article payload for a specific processing run."""
    repo = ArticleRepository()
    row = repo.get_converted_by_run_id(db, run_id=run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="converted article not found")

    article, run = row
    return _to_converted_article_read(article, run)
