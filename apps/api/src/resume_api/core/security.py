"""密码哈希、JWT、API Key 工具。"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from resume_api.core.config import Settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_token(settings: Settings, *, subject: str, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_access_token(settings: Settings, user_id: int) -> str:
    return create_token(
        settings,
        subject=str(user_id),
        token_type="access",
        expires_delta=timedelta(minutes=settings.jwt_access_minutes),
    )


def create_refresh_token(settings: Settings, user_id: int) -> str:
    return create_token(
        settings,
        subject=str(user_id),
        token_type="refresh",
        expires_delta=timedelta(days=settings.jwt_refresh_days),
    )


def decode_token(settings: Settings, token: str) -> dict[str, object]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])


def generate_api_key_plaintext() -> str:
    return "rs_" + secrets.token_urlsafe(32)


def hash_api_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def api_key_prefix(plaintext: str) -> str:
    return plaintext[:10]
