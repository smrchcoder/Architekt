from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir(database_url: str) -> None:
    if not _is_sqlite_url(database_url):
        return
    sqlite_path = make_url(database_url).database
    if not sqlite_path or sqlite_path == ":memory:":
        return
    Path(sqlite_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def _is_sqlite_url(database_url: str) -> bool:
    return make_url(database_url).get_backend_name() == "sqlite"


def _engine_options(database_url: str) -> dict[str, object]:
    options: dict[str, object] = {"pool_pre_ping": True}
    if _is_sqlite_url(database_url):
        options["connect_args"] = {"check_same_thread": False}
        return options

    options.update(
        {
            "pool_size": settings.db_pool_size,
            "max_overflow": settings.db_max_overflow,
            "pool_recycle": settings.db_pool_recycle,
        }
    )
    return options


_ensure_sqlite_dir(settings.database_url)

engine = create_engine(
    settings.database_url,
    **_engine_options(settings.database_url),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
