from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.modules.extractor.schemas import (
    KnowledgeExtractionResponse,
    KnowledgeModelValidationResponse,
    KnowledgeModelRead,
    OverviewSectionResponse,
)
from app.modules.extractor.services.extractor_service import KnowledgeExtractor
from app.modules.extractor.services.knowledge_model_validator import (
    KnowledgeModelValidationError,
    KnowledgeModelValidator,
)
from app.modules.extractor.services.overview_section_builder import (
    OverviewSectionBuilder,
)
from app.storage.db import get_db
from app.storage.models import KnowledgeModelRecord
from app.storage.repository import ArticleRepository


router = APIRouter(prefix="/extractor", tags=["extractor"])


def _to_read_model(record: KnowledgeModelRecord) -> KnowledgeModelRead:
    knowledge_model = KnowledgeModelValidator().validate_raw(record.raw_json)
    return KnowledgeModelRead(
        article_id=record.article_id,
        source_url=record.source_url,
        knowledge_model=knowledge_model,
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
    except KnowledgeModelValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors) from exc
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
    try:
        return _to_read_model(record)
    except KnowledgeModelValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors) from exc


@router.get(
    "/knowledge-models/{article_id}/validation",
    response_model=KnowledgeModelValidationResponse,
)
def validate_knowledge_model(article_id: str, db: Session = Depends(get_db)):
    service = KnowledgeExtractor()
    record = service.repo.get(db, article_id)
    if record is None:
        raise HTTPException(status_code=404, detail="knowledge model not found")

    try:
        KnowledgeModelValidator().validate_raw(record.raw_json)
    except KnowledgeModelValidationError as exc:
        return KnowledgeModelValidationResponse(
            article_id=article_id,
            valid=False,
            errors=exc.errors,
        )

    return KnowledgeModelValidationResponse(article_id=article_id, valid=True)


@router.get(
    "/knowledge-models/{article_id}/overview",
    response_model=OverviewSectionResponse,
)
def get_overview_section(article_id: str, db: Session = Depends(get_db)):
    knowledge_repo = KnowledgeExtractor().repo
    # TODo: should this be moved to service instead of trying to have it here
    knowledge_record = knowledge_repo.get(db, article_id)
    if knowledge_record is None:
        raise HTTPException(status_code=404, detail="knowledge model not found")

    article = ArticleRepository().get(db, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="article not found")
    # Todo check if this validation should be present here or not
    try:
        knowledge_model = KnowledgeModelValidator().validate_raw(
            knowledge_record.raw_json
        )
        overview = OverviewSectionBuilder().build(knowledge_model, article)
    except KnowledgeModelValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return OverviewSectionResponse(article_id=article_id, overview=overview)
