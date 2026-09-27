"""统一鉴权：JWT Bearer 或 X-Api-Key（开发环境 DEV_API_TOKEN 旁路）。"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_api.core.config import Settings, get_settings
from resume_api.core.db import get_db
from resume_api.core.security import decode_token, hash_api_key
from resume_api.models import ApiKey, User


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    role: str
    auth_via: str  # jwt | api_key | dev_token
    must_change_password: bool


def get_current_user(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
    x_api_token: str | None = Header(default=None, alias="X-Api-Token"),
) -> CurrentUser:
    """解析当前用户；失败抛 401。"""

    if settings.is_development and settings.dev_api_token:
        if x_api_key == settings.dev_api_token or x_api_token == settings.dev_api_token:
            return _ensure_dev_user(db)

    if x_api_key:
        key_hash = hash_api_key(x_api_key)
        api_key = db.scalar(
            select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.revoked_at.is_(None))
        )
        if api_key is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid api key")
        user = db.get(User, api_key.user_id)
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user inactive")
        return CurrentUser(
            id=user.id,
            username=user.username,
            role=user.role,
            auth_via="api_key",
            must_change_password=user.must_change_password,
        )

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            payload = decode_token(settings, token)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid token",
            ) from exc
        if payload.get("type") != "access":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not access token")
        user_id = int(str(payload.get("sub")))
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user inactive")
        return CurrentUser(
            id=user.id,
            username=user.username,
            role=user.role,
            auth_via="jwt",
            must_change_password=user.must_change_password,
        )

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing credentials")


def require_password_change_complete(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="password change required",
        )
    return user


def require_admin(
    user: CurrentUser = Depends(require_password_change_complete),
) -> CurrentUser:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin required")
    return user


def require_lead_or_admin(
    user: CurrentUser = Depends(require_password_change_complete),
) -> CurrentUser:
    if user.role not in {"admin", "lead"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="lead or admin required",
        )
    return user


def _ensure_dev_user(db: Session) -> CurrentUser:
    user = db.scalar(select(User).where(User.username == "dev"))
    if user is None:
        from resume_api.core.security import hash_password

        user = User(
            username="dev",
            password_hash=hash_password("dev-password-not-for-prod"),
            role="admin",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return CurrentUser(
        id=user.id,
        username=user.username,
        role=user.role,
        auth_via="dev_token",
        must_change_password=user.must_change_password,
    )
