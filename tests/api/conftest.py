from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# 测试环境变量需在导入 app 前设置
os.environ["API_TOKEN"] = "test-token"


@pytest.fixture()
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    db_path = tmp_path / "test.db"
    storage = tmp_path / "files"
    watch = tmp_path / "inbox"
    storage.mkdir()
    watch.mkdir()

    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    os.environ["STORAGE_DIR"] = str(storage)
    os.environ["WATCH_DIR"] = str(watch)
    os.environ["API_TOKEN"] = "test-token"

    from resume_api.core import config as config_mod
    from resume_api.core import db as db_mod
    from resume_api.core.config import Settings
    from resume_api.core.db import Base

    settings = Settings(
        api_token="test-token",
        database_url=f"sqlite:///{db_path.as_posix()}",
        storage_dir=str(storage),
        watch_dir=str(watch),
    )
    config_mod.get_settings = lambda: settings  # type: ignore[assignment]

    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    db_mod.engine = engine
    db_mod.SessionLocal = TestingSessionLocal

    def override_get_db() -> Generator[Session, None, None]:
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    from resume_api.main import app

    app.dependency_overrides[db_mod.get_db] = override_get_db
    # 禁用 lifespan 里的真实 watcher 干扰：TestClient 会跑 lifespan
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"X-Api-Token": "test-token"}
