from __future__ import annotations

import asyncio
import secrets
from hashlib import sha256
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import bcrypt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_session
from app.domain.enums import UserRole
from app.domain.models import DataServiceClient, User


settings = get_settings()
http_bearer = HTTPBearer(auto_error=False)
_redis_client: Redis | None = None


class TokenPayload(dict[str, Any]):
    @property
    def user_id(self) -> UUID:
        return UUID(str(self["sub"]))

    @property
    def client_id(self) -> UUID:
        return UUID(str(self["sub"]))


def generate_rsa_keypair() -> tuple[Path, Path]:
    private_path = settings.jwt_private_key_path
    public_path = settings.jwt_public_key_path

    if private_path.exists() and public_path.exists():
        return private_path, public_path

    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    private_path.write_bytes(private_pem)
    public_path.write_bytes(public_pem)
    return private_path, public_path


def get_private_key() -> str:
    generate_rsa_keypair()
    return settings.jwt_private_key_path.read_text(encoding="utf-8")


def get_public_key() -> str:
    generate_rsa_keypair()
    return settings.jwt_public_key_path.read_text(encoding="utf-8")


def get_redis_client() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    return _redis_client


async def close_redis_client() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))


async def hash_secret(secret: str, *, rounds: int = 12) -> str:
    normalized_secret = sha256(secret.encode("utf-8")).hexdigest().encode("utf-8")
    return await asyncio.to_thread(
        lambda: bcrypt.hashpw(normalized_secret, bcrypt.gensalt(rounds)).decode("utf-8")
    )


async def verify_secret(secret: str, hashed_secret: str) -> bool:
    normalized_secret = sha256(secret.encode("utf-8")).hexdigest().encode("utf-8")
    return await asyncio.to_thread(
        lambda: bcrypt.checkpw(normalized_secret, hashed_secret.encode("utf-8"))
    )


async def verify_password_async(password: str, hashed_password: str) -> bool:
    return await asyncio.to_thread(
        lambda: bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    )


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    now = datetime.now(UTC)
    expires_at = now + (expires_delta or timedelta(minutes=settings.access_token_ttl_minutes))
    payload = {
        **data,
        "exp": expires_at,
        "iat": now,
        "jti": str(uuid4()),
        "type": "access",
    }
    return jwt.encode(payload, get_private_key(), algorithm=settings.jwt_algorithm)


def create_refresh_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    now = datetime.now(UTC)
    expires_at = now + (expires_delta or timedelta(days=settings.refresh_token_ttl_days))
    payload = {
        **data,
        "exp": expires_at,
        "iat": now,
        "jti": str(uuid4()),
        "type": "refresh",
    }
    return jwt.encode(payload, get_private_key(), algorithm=settings.jwt_algorithm)


def create_data_service_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    now = datetime.now(UTC)
    expires_at = now + (expires_delta or timedelta(hours=settings.data_service_token_ttl_hours))
    payload = {
        **data,
        "exp": expires_at,
        "iat": now,
        "jti": str(uuid4()),
        "type": "data_service",
    }
    return jwt.encode(payload, get_private_key(), algorithm=settings.jwt_algorithm)


async def blacklist_token(*, jti: str, expires_at: int) -> None:
    ttl = max(expires_at - int(datetime.now(UTC).timestamp()), 1)
    await get_redis_client().set(f"blacklist:{jti}", "1", ex=ttl)


async def verify_token(token: str) -> TokenPayload:
    try:
        payload = jwt.decode(token, get_public_key(), algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        ) from exc

    jti = payload.get("jti")
    if not jti or await get_redis_client().exists(f"blacklist:{jti}"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has been revoked",
        )

    return TokenPayload(payload)


async def verify_data_service_token_payload(
    token: str,
    db_session: AsyncSession | None = None,
) -> tuple[TokenPayload, DataServiceClient | None]:
    payload = await verify_token(token)
    if payload.get("type") != "data_service":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid data-service token",
        )

    if await get_redis_client().exists(f"data-service:blacklist:client:{payload.client_id}"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Data-service client has been revoked",
        )

    if settings.token_local_validation:
        return payload, None

    if db_session is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database session is required for token validation",
        )

    result = await db_session.execute(select(DataServiceClient).where(DataServiceClient.id == payload.client_id))
    client = result.scalar_one_or_none()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Data-service client does not exist",
        )
    if client.is_revoked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Data-service client is revoked",
        )
    if client.session_token_hash is None or client.session_expires_at is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Data-service session is not active",
        )
    if client.session_expires_at <= datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Data-service session has expired",
        )
    if not await verify_secret(token, client.session_token_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Data-service session token mismatch",
        )

    return payload, client


async def verify_data_service_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    db_session: AsyncSession = Depends(get_db_session),
) -> DataServiceClient | TokenPayload:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
        )

    payload, client = await verify_data_service_token_payload(credentials.credentials, db_session=db_session)
    return client or payload


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    db_session: AsyncSession = Depends(get_db_session),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
        )

    payload = await verify_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        )

    result = await db_session.execute(select(User).where(User.id == payload.user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is inactive or does not exist",
        )
    return user


def build_token_subject(user: User) -> dict[str, Any]:
    return {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role.value if isinstance(user.role, UserRole) else str(user.role),
    }
