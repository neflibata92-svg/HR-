"""认证与用户服务。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from resume_api.core.config import Settings
from resume_api.core.security import (
    api_key_prefix,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_api_key_plaintext,
    hash_api_key,
    hash_password,
    verify_password,
)
from resume_api.models import ApiKey, User
from resume_api.schemas import AdminCreateUserRequest, RegisterRequest, TokenResponse


def count_users(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(User)) or 0)


def register_user(db: Session, settings: Settings, payload: RegisterRequest) -> User:
    if not settings.allow_register and count_users(db) > 0:
        raise PermissionError("register disabled")
    existing = db.scalar(select(User).where(User.username == payload.username))
    if existing is not None:
        raise ValueError("username taken")
    role = "admin" if count_users(db) == 0 else "member"
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def issue_tokens(settings: Settings, user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(settings, user.id),
        refresh_token=create_refresh_token(settings, user.id),
    )


def refresh_access(db: Session, settings: Settings, refresh_token: str) -> TokenResponse:
    payload = decode_token(settings, refresh_token)
    if payload.get("type") != "refresh":
        raise ValueError("not refresh token")
    user = db.get(User, int(str(payload.get("sub"))))
    if user is None or not user.is_active:
        raise ValueError("user inactive")
    return issue_tokens(settings, user)


def admin_create_user(db: Session, payload: AdminCreateUserRequest) -> User:
    existing = db.scalar(select(User).where(User.username == payload.username))
    if existing is not None:
        raise ValueError("username taken")
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_api_key(db: Session, user_id: int, name: str) -> tuple[ApiKey, str]:
    plaintext = generate_api_key_plaintext()
    row = ApiKey(
        user_id=user_id,
        name=name,
        key_prefix=api_key_prefix(plaintext),
        key_hash=hash_api_key(plaintext),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, plaintext


def list_api_keys(db: Session, user_id: int) -> list[ApiKey]:
    return list(
        db.scalars(select(ApiKey).where(ApiKey.user_id == user_id).order_by(ApiKey.id.desc())).all()
    )


def revoke_api_key(db: Session, user_id: int, key_id: int) -> ApiKey | None:
    row = db.get(ApiKey, key_id)
    if row is None or row.user_id != user_id:
        return None
    row.revoked_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row
