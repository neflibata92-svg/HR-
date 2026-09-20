"""数据库会话。"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from resume_api.core.config import Settings, get_settings


class Base(DeclarativeBase):
    """ORM 基类。"""


def create_engine_from_settings(settings: Settings):
    connect_args = {}
    if settings.database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    return create_engine(settings.database_url, connect_args=connect_args)


_settings = get_settings()
engine = create_engine_from_settings(_settings)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """创建全部表并升级已有数据库结构。"""

    from resume_api import models  # noqa: F401
    from resume_api.migrations.runner import run_migrations

    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
