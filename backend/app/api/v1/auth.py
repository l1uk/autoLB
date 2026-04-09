from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import (
    blacklist_token,
    build_token_subject,
    create_access_token,
    create_refresh_token,
    get_current_user,
    get_redis_client,
    verify_password_async,
    verify_token,
)
from app.domain.models import User


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    username: str
    role: str
    unit_id: UUID | None
    is_active: bool


async def _issue_tokens(user: User) -> TokenResponse:
    subject = build_token_subject(user)
    access_token = create_access_token(subject)
    refresh_token = create_refresh_token(subject)
    refresh_payload = await verify_token(refresh_token)
    await get_redis_client().set(
        f"refresh:current:{user.id}",
        refresh_payload["jti"],
        ex=int(refresh_payload["exp"]) - int(datetime.now(UTC).timestamp()),
    )
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: LoginRequest,
    db_session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    result = await db_session.execute(select(User).where(User.username == credentials.username))
    user = result.scalar_one_or_none()

    # TODO: Replace local-account-only auth with LDAP/AD integration when Sprint 3 starts.
    password_matches = False
    if user is not None:
        password_matches = await verify_password_async(credentials.password, user.hashed_password)

    if user is None or not user.is_active or not password_matches:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    return await _issue_tokens(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: RefreshRequest,
    db_session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    payload = await verify_token(request.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    current_jti = await get_redis_client().get(f"refresh:current:{payload.user_id}")
    if current_jti != payload["jti"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has already been rotated",
        )

    result = await db_session.execute(select(User).where(User.id == payload.user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is inactive or does not exist",
        )

    await blacklist_token(jti=payload["jti"], expires_at=int(payload["exp"]))
    return await _issue_tokens(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: LogoutRequest) -> None:
    payload = await verify_token(request.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    await blacklist_token(jti=payload["jti"], expires_at=int(payload["exp"]))
    await get_redis_client().delete(f"refresh:current:{payload.user_id}")


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        username=current_user.username,
        role=current_user.role.value,
        unit_id=current_user.unit_id,
        is_active=current_user.is_active,
    )
