from __future__ import annotations

import uuid
from collections.abc import Generator
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
import pytest_asyncio
from httpx import ASGITransport
from httpx import AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.domain import AccessPolicy
from app.domain import AccessPolicyScopeType
from app.domain import Base
from app.domain import MicroscopePicture
from app.domain import PictureType
from app.domain import Sample
from app.main import app


@pytest_asyncio.fixture
async def async_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def sample_microscope_picture() -> MicroscopePicture:
    access_policy = AccessPolicy(
        scope_type=AccessPolicyScopeType.OPEN,
        owner_id=uuid.uuid4(),
    )
    protocol_id = uuid.uuid4()
    sample = Sample(
        protocol_id=protocol_id,
        full_name="Example Sample",
        last_name="Sample",
        access_policy_id=access_policy.id,
    )
    return MicroscopePicture(
        sample_id=sample.id,
        storage_key="microscope/sample-1.dat",
        original_filename="sample-1.dat",
        sample_path="/samples/sample-1.dat",
        picture_type=PictureType.GENERIC_MICROSCOPE_PICTURE,
    )


@pytest.fixture
def mock_storage(monkeypatch: pytest.MonkeyPatch) -> Iterator[Mock]:
    client = Mock(name="mock_minio_client")
    monkeypatch.setattr("app.main.minio_client", client, raising=False)
    yield client
