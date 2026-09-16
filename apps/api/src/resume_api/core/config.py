"""应用配置。"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """内网 API 配置。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_token: str = "dev-token-change-me"
    database_url: str = "sqlite:///./data/resume.db"
    storage_dir: str = "./data/files"
    watch_dir: str = "./data/inbox"
    attachment_timeout_hours: int = 24


def get_settings() -> Settings:
    return Settings()


def ensure_data_dirs(settings: Settings) -> None:
    """确保数据库与文件目录存在。"""

    Path(settings.storage_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.watch_dir).mkdir(parents=True, exist_ok=True)
    db_path = settings.database_url.replace("sqlite:///", "")
    if db_path and not db_path.startswith(":memory:"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
