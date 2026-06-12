from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.modules.extractor.models.knowledge_model import KnowledgeModel
from app.modules.extractor.schemas import (
    KnowledgeExtractionResponse,
    KnowledgeModelRead,
)
from app.modules.extractor.services.extractor_service import KnowledgeExtractor
from app.storage.db import get_db
from app.storage.models import KnowledgeModelRecord


router = APIRouter(prefix="/extractor", tags=["extractor"])


def _to_read_model(record: KnowledgeModelRecord) -> KnowledgeModelRead:
    return KnowledgeModelRead(
        article_id=record.article_id,
        source_url=record.source_url,
        knowledge_model=KnowledgeModel.model_validate(record.raw_json),
        created_at=record.created_at,
    )


@router.post(
    "/knowledge-models/{article_id}",
    response_model=KnowledgeExtractionResponse,
)
def extract_knowledge_model(article_id: str, db: Session = Depends(get_db)):
    service = KnowledgeExtractor()
    try:
        record = service.extract_knowledge_model(db, article_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return KnowledgeExtractionResponse(extraction=_to_read_model(record))


@router.get("/knowledge-models/{article_id}", response_model=KnowledgeModelRead)
def get_knowledge_model(article_id: str, db: Session = Depends(get_db)):
    service = KnowledgeExtractor()
    record = service.repo.get(db, article_id)
    if record is None:
        raise HTTPException(status_code=404, detail="knowledge model not found")
    return _to_read_model(record)
