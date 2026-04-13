from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core import security
from app.core.database import get_db_session
from app.core.config import get_settings
from app.domain import Base
from app.main import app


@pytest_asyncio.fixture
async def integration_client() -> AsyncIterator[AsyncClient]:
    settings = get_settings()
    integration_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(integration_engine, expire_on_commit=False)

    async with integration_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    async def override_get_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    await security.close_redis_client()
    redis = security.get_redis_client()
    await redis.flushdb()
    security.settings.token_local_validation = False
    security.settings.registration_token = "test-registration-token"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    security.settings.token_local_validation = True
    await redis.flushdb()
    await security.close_redis_client()
    app.dependency_overrides.clear()
    await integration_engine.dispose()


@pytest.mark.asyncio
async def test_data_service_register_auth_and_session_with_live_services(integration_client) -> None:
    register_response = await integration_client.post(
        "/api/v1/data-service/register",
        json={
            "hostname": "acq-pc-01",
            "watch_folder": "/data/watch",
            "os_info": "Linux",
            "agent_version": "0.1.0",
        },
        headers={"X-Registration-Token": "test-registration-token"},
    )

    assert register_response.status_code == 201
    register_payload = register_response.json()
    assert register_payload["client_id"]
    assert register_payload["api_key"]

    auth_response = await integration_client.post(
        "/api/v1/data-service/auth",
        json={
            "client_id": register_payload["client_id"],
            "api_key": register_payload["api_key"],
        },
    )

    assert auth_response.status_code == 200
    auth_payload = auth_response.json()
    assert auth_payload["session_token"]
    assert auth_payload["expires_at"]

    session_response = await integration_client.get(
        "/api/v1/data-service/session",
        headers={"Authorization": f"Bearer {auth_payload['session_token']}"},
    )

    assert session_response.status_code == 200
    assert session_response.json()["client_id"] == register_payload["client_id"]


@pytest.mark.asyncio
async def test_data_service_auth_rejects_invalid_api_key_with_live_services(integration_client) -> None:
    register_response = await integration_client.post(
        "/api/v1/data-service/register",
        json={
            "hostname": "acq-pc-02",
            "watch_folder": "/data/watch",
            "os_info": "Linux",
            "agent_version": "0.1.0",
        },
        headers={"X-Registration-Token": "test-registration-token"},
    )
    client_id = register_response.json()["client_id"]

    auth_response = await integration_client.post(
        "/api/v1/data-service/auth",
        json={"client_id": client_id, "api_key": "wrong-api-key"},
    )

    assert auth_response.status_code == 401
    assert auth_response.json()["detail"] == "Invalid client credentials"
