"""简单 Token 鉴权。"""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from resume_api.core.config import get_settings


def require_api_token(x_api_token: str | None = Header(default=None)) -> None:
    """校验 X-Api-Token。"""

    expected = get_settings().api_token
    if not x_api_token or x_api_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid api token",
        )
