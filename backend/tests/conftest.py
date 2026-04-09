from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.domain import Base
from app.core.database import get_db_session
from app.core import security
from app.main import app


class FakeRedis:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self._values[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self._values.get(key)

    async def exists(self, key: str) -> int:
        return int(key in self._values)

    async def delete(self, key: str) -> int:
        existed = key in self._values
        self._values.pop(key, None)
        return int(existed)

    async def aclose(self) -> None:
        self._values.clear()


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest_asyncio.fixture
async def async_client(
    db_session: AsyncSession,
    fake_redis: FakeRedis,
    tmp_path,
) -> AsyncIterator[AsyncClient]:
    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    security._redis_client = fake_redis
    security.settings.jwt_private_key_path = tmp_path / "jwt_private.pem"
    security.settings.jwt_public_key_path = tmp_path / "jwt_public.pem"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()
    security._redis_client = None


@pytest.fixture
def mock_storage() -> Iterator[dict[str, object]]:
    with patch("boto3.client") as mock_client, patch("boto3.resource") as mock_resource:
        yield {"client": mock_client, "resource": mock_resource}
