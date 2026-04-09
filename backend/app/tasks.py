from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionFactory
from app.domain.enums import DataServiceClientStatus
from app.domain.models import DataServiceClient


async def mark_offline_clients_impl(session: AsyncSession | None = None) -> None:
    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.heartbeat_interval_seconds * 3)
    if session is not None:
        await session.execute(
            update(DataServiceClient)
            .where(
                DataServiceClient.status == DataServiceClientStatus.ONLINE,
                DataServiceClient.last_seen.is_not(None),
                DataServiceClient.last_seen < cutoff,
            )
            .values(status=DataServiceClientStatus.OFFLINE)
        )
        await session.commit()
        return

    async with AsyncSessionFactory() as managed_session:
        await mark_offline_clients_impl(managed_session)


def mark_offline_clients() -> None:
    asyncio.run(mark_offline_clients_impl())
