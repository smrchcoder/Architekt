from __future__ import annotations

from fastapi import APIRouter

from app.modules.extractor.schemas import KnowledgeModelRead


router = APIRouter(prefix="/extractor", tags=["extractor"])


@router.get("/health", response_model=KnowledgeModelRead)
def health():
    return KnowledgeModelRead(id="noop", status="ok")

