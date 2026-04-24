from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core import security
from app.core.config import get_settings
from app.core.database import get_db_session
from app.domain import Base
from app.domain.enums import DataServiceTaskStatus
from app.domain.models import DataServiceTask
from app.main import app


@pytest_asyncio.fixture
async def live_app_client() -> AsyncIterator[tuple[AsyncClient, async_sessionmaker]]:
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
        yield client, session_factory

    security.settings.token_local_validation = True
    await redis.flushdb()
    await security.close_redis_client()
    app.dependency_overrides.clear()
    await integration_engine.dispose()


@pytest.mark.asyncio
async def test_heartbeat_delivers_pending_tasks_with_live_services(live_app_client) -> None:
    client, session_factory = live_app_client

    register_response = await client.post(
        "/api/v1/data-service/register",
        json={
            "hostname": "acq-pc-01",
            "watch_folder": "/data/watch",
            "os_info": "Linux",
            "agent_version": "0.1.0",
            "registration_secret": "test-registration-token",
        },
        headers={"X-Registration-Token": "test-registration-token"},
    )
    register_payload = register_response.json()
    auth_response = await client.post(
        "/api/v1/data-service/auth",
        json={"client_id": register_payload["client_id"], "api_key": register_payload["api_key"]},
    )
    session_token = auth_response.json()["session_token"]

    async with session_factory() as db_session:
        task = DataServiceTask(
            client_id=UUID(register_payload["client_id"]),
            task_type="CREATE_DIR",
            operation="mkdir",
            params={"path": "/opaque"},
            status=DataServiceTaskStatus.PENDING,
        )
        db_session.add(task)
        await db_session.commit()
        task_id = str(task.id)

    heartbeat_response = await client.post(
        "/api/v1/data-service/heartbeat",
        json={
            "client_id": register_payload["client_id"],
            "agent_version": "0.2.0",
            "status_info": {"queue_depth": 1},
        },
        headers={"Authorization": f"Bearer {session_token}"},
    )

    assert heartbeat_response.status_code == 200
    payload = heartbeat_response.json()
    assert payload["tasks"][0]["id"] == task_id

    async with session_factory() as db_session:
        persisted_task = await db_session.scalar(
            select(DataServiceTask).where(DataServiceTask.id == UUID(task_id))
        )
        assert persisted_task is not None
        assert persisted_task.status == DataServiceTaskStatus.DELIVERED
        assert persisted_task.delivered_at is not None


@pytest.mark.asyncio
async def test_task_ack_updates_task_status_with_live_services(live_app_client) -> None:
    client, session_factory = live_app_client

    register_response = await client.post(
        "/api/v1/data-service/register",
        json={
            "hostname": "acq-pc-02",
            "watch_folder": "/data/watch",
            "os_info": "Linux",
            "agent_version": "0.1.0",
            "registration_secret": "test-registration-token",
        },
        headers={"X-Registration-Token": "test-registration-token"},
    )
    register_payload = register_response.json()
    auth_response = await client.post(
        "/api/v1/data-service/auth",
        json={"client_id": register_payload["client_id"], "api_key": register_payload["api_key"]},
    )
    session_token = auth_response.json()["session_token"]

    async with session_factory() as db_session:
        task = DataServiceTask(
            client_id=UUID(register_payload["client_id"]),
            task_type="SCAN",
            operation="collect",
            params={"context_id": "opaque"},
            status=DataServiceTaskStatus.DELIVERED,
            delivered_at=datetime.now(UTC),
        )
        db_session.add(task)
        await db_session.commit()
        task_id = str(task.id)

    ack_response = await client.post(
        "/api/v1/data-service/task-ack",
        json={"task_id": task_id, "status": "SUCCESS"},
        headers={"Authorization": f"Bearer {session_token}"},
    )

    assert ack_response.status_code == 204

    async with session_factory() as db_session:
        persisted_task = await db_session.scalar(
            select(DataServiceTask).where(DataServiceTask.id == UUID(task_id))
        )
        assert persisted_task is not None
        assert persisted_task.status == DataServiceTaskStatus.SUCCESS
        assert persisted_task.completed_at is not None
