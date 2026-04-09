from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core import security
from app.core.security import hash_secret
from app.domain.enums import DataServiceClientStatus
from app.domain.models import DataServiceClient


async def create_data_service_client(
    db_session,
    *,
    api_key: str = "machine-secret",
    is_revoked: bool = False,
) -> tuple[DataServiceClient, str]:
    client = DataServiceClient(
        id=uuid4(),
        hostname="acq-pc-01",
        watch_folder="C:/watch",
        os_info="Windows 11",
        agent_version="0.1.0",
        api_key_hash=await hash_secret(api_key, rounds=12),
        status=DataServiceClientStatus.NEVER_SEEN,
        is_revoked=is_revoked,
    )
    db_session.add(client)
    await db_session.commit()
    return client, api_key


@pytest.mark.asyncio
async def test_data_service_register_happy_path(async_client, db_session) -> None:
    response = await async_client.post(
        "/api/v1/data-service/register",
        json={
            "hostname": "acq-pc-01",
            "watch_folder": "C:/watch",
            "os_info": "Windows 11",
            "agent_version": "0.1.0",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["client_id"]
    assert payload["api_key"]

    result = await db_session.execute(
        select(DataServiceClient).where(DataServiceClient.id == UUID(payload["client_id"]))
    )
    client = result.scalar_one()
    assert client.api_key_hash != payload["api_key"]
    assert client.status == DataServiceClientStatus.NEVER_SEEN


@pytest.mark.asyncio
async def test_data_service_auth_happy_path(async_client, db_session) -> None:
    client, api_key = await create_data_service_client(db_session)

    response = await async_client.post(
        "/api/v1/data-service/auth",
        json={"client_id": str(client.id), "api_key": api_key},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_token"]
    assert payload["expires_at"]

    result = await db_session.execute(select(DataServiceClient).where(DataServiceClient.id == client.id))
    refreshed_client = result.scalar_one()
    assert refreshed_client.session_token_hash is not None
    assert refreshed_client.status == DataServiceClientStatus.ONLINE


@pytest.mark.asyncio
async def test_data_service_auth_rejects_bad_api_key(async_client, db_session) -> None:
    client, _ = await create_data_service_client(db_session)

    response = await async_client.post(
        "/api/v1/data-service/auth",
        json={"client_id": str(client.id), "api_key": "wrong-secret"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid client credentials"


@pytest.mark.asyncio
async def test_data_service_auth_rejects_revoked_client(async_client, db_session) -> None:
    client, api_key = await create_data_service_client(db_session, is_revoked=True)

    response = await async_client.post(
        "/api/v1/data-service/auth",
        json={"client_id": str(client.id), "api_key": api_key},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Data-service client is revoked"


@pytest.mark.asyncio
async def test_data_service_protected_endpoint_happy_path(async_client, db_session) -> None:
    security.settings.token_local_validation = False
    client, api_key = await create_data_service_client(db_session)
    auth_response = await async_client.post(
        "/api/v1/data-service/auth",
        json={"client_id": str(client.id), "api_key": api_key},
    )
    session_token = auth_response.json()["session_token"]

    response = await async_client.get(
        "/api/v1/data-service/session",
        headers={"Authorization": f"Bearer {session_token}"},
    )

    security.settings.token_local_validation = True

    assert response.status_code == 200
    assert response.json()["client_id"] == str(client.id)


@pytest.mark.asyncio
async def test_data_service_protected_endpoint_rejects_invalid_token(async_client) -> None:
    response = await async_client.get(
        "/api/v1/data-service/session",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
