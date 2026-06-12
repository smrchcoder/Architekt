from sqlalchemy.orm import Session
from sqlalchemy import select
from app.storage.models import KnowledgeModelRecord


class KnowledgeModelRepository:
    def create(
        self, db: Session, knowledge_model: KnowledgeModelRecord
    ) -> KnowledgeModelRecord:
        db.add(knowledge_model)
        db.commit()
        db.refresh(knowledge_model)
        return knowledge_model

    def get(self, db: Session, article_id: str) -> KnowledgeModelRecord | None:
        return db.get(KnowledgeModelRecord, article_id)

    def get_by_source_url(
        self, db: Session, source_url: str
    ) -> KnowledgeModelRecord | None:
        return db.execute(
            select(KnowledgeModelRecord).where(
                KnowledgeModelRecord.source_url == source_url
            )
        ).scalar_one_or_none()
