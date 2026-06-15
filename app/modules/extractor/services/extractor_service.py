from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.llm import LLMClient
from app.modules.extractor.models.knowledge_model import KnowledgeModel
from app.modules.extractor.repository import KnowledgeModelRepository
from app.modules.extractor.prompts.knowledge_extraction import (
    KNOWLEDGE_EXTRACTION_SYSTEM_PROMPT,
    build_user_prompt,
)
from app.modules.extractor.services.knowledge_model_validator import (
    KnowledgeModelValidator,
)
from app.storage.repository import ArticleRepository
from app.storage.models import KnowledgeModelRecord


class KnowledgeExtractor:
    def __init__(
        self,
        repo: KnowledgeModelRepository | None = None,
        article_repo: ArticleRepository | None = None,
        llm_client: LLMClient | None = None,
        validator: KnowledgeModelValidator | None = None,
    ) -> None:
        self.repo = repo or KnowledgeModelRepository()
        self.article_repo = article_repo or ArticleRepository()
        self.llm_client = llm_client or LLMClient()
        self.validator = validator or KnowledgeModelValidator()

    def extract_knowledge_model(
        self, db: Session, article_id: str
    ) -> KnowledgeModelRecord:
        if not article_id:
            raise ValueError("article_id is required for extraction")

        existing = self.repo.get(db, article_id=article_id)
        if existing is not None:
            return existing

        article = self.article_repo.get(db, article_id=article_id)
        if article is None:
            raise LookupError("article not found")
        if not article.cleaned_text:
            raise ValueError("article has no cleaned_text to extract from")

        result = self.llm_client.extract_structured(
            system_prompt=KNOWLEDGE_EXTRACTION_SYSTEM_PROMPT,
            user_prompt=build_user_prompt(
                cleaned_text=article.cleaned_text,
                source_title=article.source_title,
                source_domain=article.source_domain,
                word_count=article.word_count,
            ),
            response_model=KnowledgeModel,
            model=settings.extraction_model,
        )
        self.validator.validate(result)
        record = KnowledgeModelRecord(
            article_id=article.article_id,
            source_url=article.source_url,
            raw_json=result.model_dump(mode="json"),
        )
        return self.repo.create(db, record)
