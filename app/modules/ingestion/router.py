from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.modules.ingestion.schemas import ArticleCreate, ArticleIngestResponse, ArticleRead
from app.modules.ingestion.service import IngestionService
from app.storage.db import get_db
from app.storage.repository import ArticleRepository


router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/articles", response_model=ArticleIngestResponse)
def ingest_article(payload: ArticleCreate, db: Session = Depends(get_db)):
    service = IngestionService()
    article = service.ingest_article(db, payload)
    return ArticleIngestResponse(
        article=ArticleRead(
            unique_id=article.unique_id,
            source_url=article.source_url,
            raw_text=article.raw_text,
            word_count=article.word_count,
            processing_time=article.processing_time,
            source_title=article.source_title,
            source_domain=article.source_domain,
        )
    )


@router.get("/articles/{unique_id}", response_model=ArticleRead)
def get_article(unique_id: str, db: Session = Depends(get_db)):
    repo = ArticleRepository()
    article = repo.get(db, unique_id)
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return ArticleRead(
        unique_id=article.unique_id,
        source_url=article.source_url,
        raw_text=article.raw_text,
        word_count=article.word_count,
        processing_time=article.processing_time,
        source_title=article.source_title,
        source_domain=article.source_domain,
    )

