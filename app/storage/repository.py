from sqlalchemy.orm import Session
from sqlalchemy import select

from app.storage.models import Article


class ArticleRepository:
    def create(self, db: Session, article: Article) -> Article:
        db.add(article)
        db.commit()
        db.refresh(article)
        return article

    def get(self, db: Session, article_id: str) -> Article | None:
        return db.get(Article, article_id)

    def get_by_source_url(self, db: Session, source_url: str) -> Article | None:
        return db.execute(
            select(Article).where(Article.source_url == source_url)
        ).scalar_one_or_none()
