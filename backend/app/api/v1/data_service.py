from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.security import verify_data_service_token
from app.domain.enums import DataServiceClientStatus, DataServiceTaskStatus
from app.domain.models import DataServiceClient, DataServiceTask


router = APIRouter(prefix="/data-service", tags=["data-service"])


class HeartbeatRequest(BaseModel):
    client_id: UUID
    agent_version: str
    status_info: dict[str, str | int | float | bool | None]


class HeartbeatTaskResponse(BaseModel):
    id: UUID
    task_type: str
    operation: str
    params: dict


class HeartbeatResponse(BaseModel):
    tasks: list[HeartbeatTaskResponse]


class VersionResponse(BaseModel):
    latest_version: str
    auto_update_enabled: bool


class TaskAckRequest(BaseModel):
    task_id: UUID
    status: DataServiceTaskStatus
    error_message: str | None = None


@router.get("/version", response_model=VersionResponse)
async def data_service_version(
    principal: DataServiceClient | object = Depends(verify_data_service_token),
) -> VersionResponse:
    _ = principal
    settings = get_settings()
    latest_version = settings.data_service_latest_version or "0.1.0"
    return VersionResponse(
        latest_version=latest_version,
        auto_update_enabled=settings.data_service_auto_update_enabled,
    )


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def data_service_heartbeat(
    payload: HeartbeatRequest,
    principal: DataServiceClient | object = Depends(verify_data_service_token),
    db_session: AsyncSession = Depends(get_db_session),
) -> HeartbeatResponse:
    principal_client_id = principal.id if isinstance(principal, DataServiceClient) else UUID(str(principal["sub"]))
    if payload.client_id != principal_client_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Heartbeat client_id does not match authenticated client",
        )

    result = await db_session.execute(select(DataServiceClient).where(DataServiceClient.id == payload.client_id))
    client = result.scalar_one_or_none()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data-service client not found",
        )

    now = datetime.now(UTC)
    client.last_seen = now
    client.status = DataServiceClientStatus.ONLINE
    client.agent_version = payload.agent_version

    task_result = await db_session.execute(
        select(DataServiceTask).where(
            DataServiceTask.client_id == payload.client_id,
            DataServiceTask.status == DataServiceTaskStatus.PENDING,
        )
    )
    tasks = list(task_result.scalars().all())
    for task in tasks:
        task.status = DataServiceTaskStatus.DELIVERED
        task.delivered_at = now

    await db_session.commit()
    return HeartbeatResponse(
        tasks=[
            HeartbeatTaskResponse(
                id=task.id,
                task_type=task.task_type,
                operation=task.operation,
                params=task.params,
            )
            for task in tasks
        ]
    )


@router.post("/task-ack", status_code=status.HTTP_204_NO_CONTENT)
async def acknowledge_data_service_task(
    payload: TaskAckRequest,
    principal: DataServiceClient | object = Depends(verify_data_service_token),
    db_session: AsyncSession = Depends(get_db_session),
) -> None:
    if payload.status not in {DataServiceTaskStatus.SUCCESS, DataServiceTaskStatus.ERROR}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Task acknowledgement status must be SUCCESS or ERROR",
        )

    principal_client_id = principal.id if isinstance(principal, DataServiceClient) else UUID(str(principal["sub"]))
    result = await db_session.execute(select(DataServiceTask).where(DataServiceTask.id == payload.task_id))
    task = result.scalar_one_or_none()
    if task is None or task.client_id != principal_client_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data-service task not found",
        )

    final_status = payload.status
    error_message = payload.error_message
    if (
        task.task_type == "CREATE_DIR"
        and payload.status == DataServiceTaskStatus.ERROR
        and payload.error_message == "directory already exists"
    ):
        final_status = DataServiceTaskStatus.SUCCESS
        error_message = None

    task.status = final_status
    task.completed_at = datetime.now(UTC)
    task.error_message = error_message
    await db_session.commit()
