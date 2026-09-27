"""应用配置。"""

from __future__ import annotations

from pathlib import Path

from pydantic import model_validator
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
    # 仅 API 服务端持有，禁止下发到 Web 或本机 Agent
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 60.0
    llm_max_attempts: int = 3

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.is_development:
            return self
        if self.jwt_secret == "change-me-jwt-secret" or len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must be a non-default value of at least 32 characters")
        origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        if "*" in origins:
            raise ValueError("CORS_ORIGINS must list explicit production origins")
        return self

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
