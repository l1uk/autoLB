from __future__ import annotations

import hmac as hmac_lib
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.security import (
    create_data_service_token,
    generate_api_key,
    hash_secret,
    verify_data_service_token,
    verify_secret,
)
from app.domain.enums import DataServiceClientStatus
from app.domain.models import DataServiceClient


settings = get_settings()
router = APIRouter(prefix="/data-service", tags=["data-service-auth"])
protected_router = APIRouter(prefix="/data-service", tags=["data-service-auth"])


class DataServiceRegisterRequest(BaseModel):
    hostname: str
    watch_folder: str
    os_info: str
    agent_version: str
    registration_secret: str


class DataServiceRegisterResponse(BaseModel):
    client_id: UUID
    api_key: str


class DataServiceAuthRequest(BaseModel):
    client_id: UUID
    api_key: str


class DataServiceAuthResponse(BaseModel):
    session_token: str
    expires_at: datetime


@router.post(
    "/register",
    response_model=DataServiceRegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_data_service_client(
    payload: DataServiceRegisterRequest,
    db_session: AsyncSession = Depends(get_db_session),
) -> DataServiceRegisterResponse:
    """
    Register a new data-service client (RFC-14).
    
    Validates registration_secret using constant-time comparison (SEC-1, §8.1).
    The registration_secret must match the REGISTRATION_SECRET environment variable
    and must be provided out-of-band to the data-service installer.
    
    Raises HTTPException(403) if registration_secret is invalid.
    """
    # FIRST operation: validate registration_secret using constant-time comparison (SEC-1)
    if not hmac_lib.compare_digest(
        payload.registration_secret.encode("utf-8"),
        settings.REGISTRATION_SECRET.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid registration_secret",
        )

    api_key = generate_api_key()
    client = DataServiceClient(
        hostname=payload.hostname,
        watch_folder=payload.watch_folder,
        os_info=payload.os_info,
        agent_version=payload.agent_version,
        api_key_hash=await hash_secret(api_key, rounds=12),
        status=DataServiceClientStatus.NEVER_SEEN,
        is_revoked=False,
    )
    db_session.add(client)
    await db_session.commit()
    await db_session.refresh(client)

    return DataServiceRegisterResponse(client_id=client.id, api_key=api_key)


@router.post("/auth", response_model=DataServiceAuthResponse)
async def authenticate_data_service_client(
    payload: DataServiceAuthRequest,
    db_session: AsyncSession = Depends(get_db_session),
) -> DataServiceAuthResponse:
    result = await db_session.execute(select(DataServiceClient).where(DataServiceClient.id == payload.client_id))
    client = result.scalar_one_or_none()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid client credentials",
        )
    if client.is_revoked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Data-service client is revoked",
        )
    if not await verify_secret(payload.api_key, client.api_key_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid client credentials",
        )

    session_token = create_data_service_token({"sub": str(client.id), "hostname": client.hostname})
    expires_at = datetime.now(UTC) + timedelta(hours=settings.data_service_token_ttl_hours)
    client.session_token_hash = await hash_secret(session_token, rounds=12)
    client.session_expires_at = expires_at
    client.status = DataServiceClientStatus.ONLINE
    await db_session.commit()

    return DataServiceAuthResponse(session_token=session_token, expires_at=expires_at)


@protected_router.get("/session")
async def get_data_service_session(
    principal: DataServiceClient | object = Depends(verify_data_service_token),
) -> dict[str, str]:
    client_id = str(principal.id) if isinstance(principal, DataServiceClient) else str(principal["sub"])
    return {"client_id": client_id}
