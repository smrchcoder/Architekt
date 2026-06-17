from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.modules.ingestion.schema.article_schema import (
    ArticleCreate,
    ArticleIngestResponse,
    ArticleRead,
)
from app.modules.ingestion.services.ingestion_service import IngestionService
from app.storage.db import get_db
from app.storage.repository import ArticleRepository


router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/articles", response_model=ArticleIngestResponse)
def ingest_article(payload: ArticleCreate, db: Session = Depends(get_db)):
    service = IngestionService()
    try:
        article = service.ingest_article(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ArticleIngestResponse(
        article=ArticleRead(
            article_id=article.article_id,
            source_url=article.source_url,
            raw_text=article.raw_text,
            cleaned_text=article.cleaned_text,
            word_count=article.word_count,
            processing_time=article.processing_time,
            source_title=article.source_title,
            source_domain=article.source_domain,
            media_items=article.media_items,
            extraction_warnings=article.extraction_warnings,
        )
    )


@router.get("/articles/{article_id}", response_model=ArticleRead)
def get_article(article_id: str, db: Session = Depends(get_db)):
    repo = ArticleRepository()
    article = repo.get(db, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return ArticleRead(
        article_id=article.article_id,
        source_url=article.source_url,
        raw_text=article.raw_text,
        cleaned_text=article.cleaned_text,
        word_count=article.word_count,
        processing_time=article.processing_time,
        source_title=article.source_title,
        source_domain=article.source_domain,
        media_items=article.media_items,
        extraction_warnings=article.extraction_warnings,
    )
