"""应用配置。"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """API 配置（云端 / 本地）。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"
    database_url: str = "sqlite:///./data/resume.db"
    storage_dir: str = "./data/files"
    watch_dir: str = "./data/inbox"
    attachment_timeout_hours: int = 24
    jwt_secret: str = "change-me-jwt-secret"
    jwt_access_minutes: int = 120
    jwt_refresh_days: int = 14
    allow_register: bool = True
    cors_origins: str = "*"
    # 仅 ENV=development 生效的旁路 Token（兼容旧测试 / 本地调试）
    dev_api_token: str = "dev-token-change-me"
    # 已废弃：生产勿依赖；保留字段以免旧 .env 报错
    api_token: str = ""

    @property
    def is_development(self) -> bool:
        return self.env.lower() in {"development", "dev", "test"}


def get_settings() -> Settings:
    return Settings()


def ensure_data_dirs(settings: Settings) -> None:
    """确保数据库与文件目录存在。"""

    Path(settings.storage_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.watch_dir).mkdir(parents=True, exist_ok=True)
    db_path = settings.database_url.replace("sqlite:///", "")
    if db_path and not db_path.startswith(":memory:"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
