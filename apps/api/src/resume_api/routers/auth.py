"""认证路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from resume_api.core.auth import (
    CurrentUser,
    get_current_user,
    require_admin,
    require_password_change_complete,
)
from resume_api.core.config import Settings, get_settings
from resume_api.core.db import get_db
from resume_api.schemas import (
    AdminCreateUserRequest,
    ApiKeyCreateRequest,
    ApiKeyCreatedOut,
    ApiKeyOut,
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
    UserStatusRequest,
)
from resume_api.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    try:
        user = auth_service.register_user(db, settings, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return auth_service.issue_tokens(settings, user)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    user = auth_service.authenticate(db, payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    return auth_service.issue_tokens(settings, user)


@router.post("/change-password", response_model=TokenResponse)
def change_password(
    payload: ChangePasswordRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    if user.auth_via != "jwt":
        raise HTTPException(status_code=403, detail="jwt authentication required")
    try:
        row = auth_service.change_password(
            db,
            user.id,
            payload.current_password,
            payload.new_password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return auth_service.issue_tokens(settings, row)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    payload: RefreshRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    try:
        return auth_service.refresh_access(db, settings, payload.refresh_token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh") from exc


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    from resume_api.models import User

    row = db.get(User, user.id)
    if row is None:
        raise HTTPException(status_code=404, detail="user not found")
    return UserOut.model_validate(row)


@router.get("/users", response_model=list[UserOut])
def admin_list_users(
    _: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[UserOut]:
    return [UserOut.model_validate(user) for user in auth_service.list_users(db)]


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def admin_create_user(
    payload: AdminCreateUserRequest,
    _: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserOut:
    try:
        user = auth_service.admin_create_user(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}/status", response_model=UserOut)
def admin_set_user_status(
    user_id: int,
    payload: UserStatusRequest,
    _: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserOut:
    try:
        user = auth_service.set_member_status(db, user_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return UserOut.model_validate(user)


@router.post("/users/{user_id}/reset-password", response_model=UserOut)
def admin_reset_user_password(
    user_id: int,
    payload: ResetPasswordRequest,
    _: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserOut:
    try:
        user = auth_service.reset_member_password(db, user_id, payload.temporary_password)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return UserOut.model_validate(user)


@router.post("/api-keys", response_model=ApiKeyCreatedOut)
def create_api_key(
    payload: ApiKeyCreateRequest,
    user: CurrentUser = Depends(require_password_change_complete),
    db: Session = Depends(get_db),
) -> ApiKeyCreatedOut:
    row, plaintext = auth_service.create_api_key(db, user.id, payload.name)
    return ApiKeyCreatedOut(
        id=row.id,
        name=row.name,
        key_prefix=row.key_prefix,
        api_key=plaintext,
        created_at=row.created_at,
    )


@router.get("/api-keys", response_model=list[ApiKeyOut])
def list_api_keys(
    user: CurrentUser = Depends(require_password_change_complete),
    db: Session = Depends(get_db),
) -> list[ApiKeyOut]:
    return [ApiKeyOut.model_validate(k) for k in auth_service.list_api_keys(db, user.id)]


@router.delete("/api-keys/{key_id}", response_model=ApiKeyOut)
def revoke_api_key(
    key_id: int,
    user: CurrentUser = Depends(require_password_change_complete),
    db: Session = Depends(get_db),
) -> ApiKeyOut:
    row = auth_service.revoke_api_key(db, user.id, key_id)
    if row is None:
        raise HTTPException(status_code=404, detail="api key not found")
    return ApiKeyOut.model_validate(row)
