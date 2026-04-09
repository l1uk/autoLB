from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core import security
from app.domain.enums import DataServiceClientStatus, DataServiceTaskStatus
from app.domain.models import DataServiceClient, DataServiceTask
from app.tasks import mark_offline_clients_impl


async def create_authenticated_client(db_session) -> tuple[DataServiceClient, str]:
    client = DataServiceClient(
        id=uuid4(),
        hostname="acq-pc-01",
        watch_folder="C:/watch",
        os_info="Windows 11",
        agent_version="0.1.0",
        api_key_hash=await security.hash_secret("api-key"),
        status=DataServiceClientStatus.ONLINE,
        is_revoked=False,
    )
    db_session.add(client)
    await db_session.commit()

    token = security.create_data_service_token({"sub": str(client.id), "hostname": client.hostname})
    client.session_token_hash = await security.hash_secret(token)
    client.session_expires_at = datetime.now(UTC) + timedelta(hours=8)
    await db_session.commit()
    return client, token


@pytest.mark.asyncio
async def test_heartbeat_happy_path(async_client, db_session) -> None:
    security.settings.token_local_validation = False
    client, token = await create_authenticated_client(db_session)
    pending_task = DataServiceTask(
        client_id=client.id,
        task_type="CREATE_DIR",
        operation="mkdir",
        params={"path": "/opaque"},
        status=DataServiceTaskStatus.PENDING,
    )
    db_session.add(pending_task)
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/data-service/heartbeat",
        json={
            "client_id": str(client.id),
            "agent_version": "0.2.0",
            "status_info": {"queue_depth": 1},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    security.settings.token_local_validation = True

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["tasks"]) == 1
    assert payload["tasks"][0]["id"] == str(pending_task.id)
    assert "protocol_id" not in payload["tasks"][0]

    refreshed_client = await db_session.get(DataServiceClient, client.id)
    refreshed_task = await db_session.get(DataServiceTask, pending_task.id)
    assert refreshed_client.agent_version == "0.2.0"
    assert refreshed_client.status == DataServiceClientStatus.ONLINE
    assert refreshed_client.last_seen is not None
    assert refreshed_task.status == DataServiceTaskStatus.DELIVERED
    assert refreshed_task.delivered_at is not None


@pytest.mark.asyncio
async def test_heartbeat_rejects_client_id_mismatch(async_client, db_session) -> None:
    security.settings.token_local_validation = False
    client, token = await create_authenticated_client(db_session)

    response = await async_client.post(
        "/api/v1/data-service/heartbeat",
        json={
            "client_id": str(uuid4()),
            "agent_version": "0.2.0",
            "status_info": {"queue_depth": 1},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    security.settings.token_local_validation = True

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_task_ack_happy_path(async_client, db_session) -> None:
    security.settings.token_local_validation = False
    client, token = await create_authenticated_client(db_session)
    delivered_task = DataServiceTask(
        client_id=client.id,
        task_type="SCAN",
        operation="collect",
        params={"context_id": "opaque"},
        status=DataServiceTaskStatus.DELIVERED,
    )
    db_session.add(delivered_task)
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/data-service/task-ack",
        json={"task_id": str(delivered_task.id), "status": "SUCCESS"},
        headers={"Authorization": f"Bearer {token}"},
    )
    security.settings.token_local_validation = True

    assert response.status_code == 204
    refreshed_task = await db_session.get(DataServiceTask, delivered_task.id)
    assert refreshed_task.status == DataServiceTaskStatus.SUCCESS
    assert refreshed_task.completed_at is not None
    assert refreshed_task.error_message is None


@pytest.mark.asyncio
async def test_task_ack_create_dir_directory_exists_is_idempotent(async_client, db_session) -> None:
    security.settings.token_local_validation = False
    client, token = await create_authenticated_client(db_session)
    delivered_task = DataServiceTask(
        client_id=client.id,
        task_type="CREATE_DIR",
        operation="mkdir",
        params={"path": "/opaque"},
        status=DataServiceTaskStatus.DELIVERED,
    )
    db_session.add(delivered_task)
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/data-service/task-ack",
        json={
            "task_id": str(delivered_task.id),
            "status": "ERROR",
            "error_message": "directory already exists",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    security.settings.token_local_validation = True

    assert response.status_code == 204
    refreshed_task = await db_session.get(DataServiceTask, delivered_task.id)
    assert refreshed_task.status == DataServiceTaskStatus.SUCCESS
    assert refreshed_task.error_message is None


@pytest.mark.asyncio
async def test_task_ack_rejects_wrong_client(async_client, db_session) -> None:
    security.settings.token_local_validation = False
    client, token = await create_authenticated_client(db_session)
    other_client = DataServiceClient(
        id=uuid4(),
        hostname="acq-pc-02",
        watch_folder="C:/watch2",
        os_info="Windows 11",
        agent_version="0.1.0",
        api_key_hash=await security.hash_secret("api-key-2"),
        status=DataServiceClientStatus.ONLINE,
        is_revoked=False,
    )
    db_session.add(other_client)
    await db_session.commit()
    task = DataServiceTask(
        client_id=other_client.id,
        task_type="SCAN",
        operation="collect",
        params={"context_id": "opaque"},
        status=DataServiceTaskStatus.DELIVERED,
    )
    db_session.add(task)
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/data-service/task-ack",
        json={"task_id": str(task.id), "status": "SUCCESS"},
        headers={"Authorization": f"Bearer {token}"},
    )
    security.settings.token_local_validation = True

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_mark_offline_clients_impl(db_session) -> None:
    stale_client = DataServiceClient(
        id=uuid4(),
        hostname="acq-pc-01",
        watch_folder="C:/watch",
        os_info="Windows 11",
        agent_version="0.1.0",
        api_key_hash=await security.hash_secret("api-key"),
        status=DataServiceClientStatus.ONLINE,
        last_seen=datetime.now(UTC) - timedelta(seconds=120),
        is_revoked=False,
    )
    fresh_client = DataServiceClient(
        id=uuid4(),
        hostname="acq-pc-02",
        watch_folder="C:/watch2",
        os_info="Windows 11",
        agent_version="0.1.0",
        api_key_hash=await security.hash_secret("api-key-2"),
        status=DataServiceClientStatus.ONLINE,
        last_seen=datetime.now(UTC),
        is_revoked=False,
    )
    db_session.add_all([stale_client, fresh_client])
    await db_session.commit()

    await mark_offline_clients_impl(db_session)

    await db_session.refresh(stale_client)
    await db_session.refresh(fresh_client)
    assert stale_client.status == DataServiceClientStatus.OFFLINE
    assert fresh_client.status == DataServiceClientStatus.ONLINE
