from sqlalchemy.orm import Session
from sqlalchemy import select

from app.storage.models import Article, ProcessingRun


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

    def get_converted(
        self, db: Session, *, limit: int, offset: int
    ) -> list[tuple[Article, ProcessingRun]]:
        """Return all articles that have at least one completed ProcessingRun with sections."""
        stmt = (
            select(Article, ProcessingRun)
            .join(ProcessingRun, Article.article_id == ProcessingRun.article_id)
            .where(
                ProcessingRun.status == "completed",
                ProcessingRun.section_1_json.isnot(None),
            )
            .order_by(ProcessingRun.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return db.execute(stmt).all()

    def get_converted_by_run_id(
        self, db: Session, run_id: str
    ) -> tuple[Article, ProcessingRun] | None:
        """Return the converted article payload for a specific completed run."""
        stmt = (
            select(Article, ProcessingRun)
            .join(ProcessingRun, Article.article_id == ProcessingRun.article_id)
            .where(
                ProcessingRun.run_id == run_id,
                ProcessingRun.status == "completed",
                ProcessingRun.section_1_json.isnot(None),
            )
        )
        return db.execute(stmt).one_or_none()
