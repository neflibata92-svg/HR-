from __future__ import annotations

import pytest
from pydantic import ValidationError

from resume_api.core.config import Settings


def test_production_rejects_default_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(env="production", jwt_secret="change-me-jwt-secret", cors_origins="https://hr.example.test")


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(env="production", jwt_secret="a-long-random-production-secret-value", cors_origins="*")

    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(
            env="production",
            jwt_secret="a-long-random-production-secret-value",
            cors_origins="https://hr.example.test,*",
        )


def test_production_accepts_explicit_security_settings() -> None:
    settings = Settings(
        env="production",
        jwt_secret="a-long-random-production-secret-value",
        cors_origins="https://hr.example.test",
        allow_register=False,
        dev_api_token="",
    )

    assert settings.is_development is False
