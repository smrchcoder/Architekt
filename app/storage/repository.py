from __future__ import annotations

from sqlalchemy.orm import Session

from app.storage.models import Article


class ArticleRepository:
    def create(self, db: Session, article: Article) -> Article:
        db.add(article)
        db.commit()
        db.refresh(article)
        return article

    def get(self, db: Session, unique_id: str) -> Article | None:
        return db.get(Article, unique_id)

