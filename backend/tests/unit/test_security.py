from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core import security
from app.domain.enums import DataServiceClientStatus
from app.domain.models import DataServiceClient


def test_generate_rsa_keypair_creates_files(tmp_path) -> None:
    security.settings.jwt_private_key_path = tmp_path / "private.pem"
    security.settings.jwt_public_key_path = tmp_path / "public.pem"

    private_path, public_path = security.generate_rsa_keypair()

    assert private_path.exists()
    assert public_path.exists()
    assert "BEGIN PRIVATE KEY" in private_path.read_text(encoding="utf-8")
    assert "BEGIN PUBLIC KEY" in public_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_create_access_token_and_verify_token(fake_redis, tmp_path) -> None:
    security._redis_client = fake_redis
    security.settings.jwt_private_key_path = tmp_path / "private.pem"
    security.settings.jwt_public_key_path = tmp_path / "public.pem"

    token = security.create_access_token({"sub": str(uuid4()), "username": "alice"})
    payload = await security.verify_token(token)

    assert payload["type"] == "access"
    assert payload["username"] == "alice"


@pytest.mark.asyncio
async def test_verify_token_rejects_blacklisted_token(fake_redis, tmp_path) -> None:
    security._redis_client = fake_redis
    security.settings.jwt_private_key_path = tmp_path / "private.pem"
    security.settings.jwt_public_key_path = tmp_path / "public.pem"

    token = security.create_access_token({"sub": str(uuid4()), "username": "alice"})
    payload = await security.verify_token(token)
    await security.blacklist_token(
        jti=payload["jti"],
        expires_at=int((datetime.now(UTC) + timedelta(minutes=15)).timestamp()),
    )

    with pytest.raises(HTTPException, match="revoked"):
        await security.verify_token(token)


@pytest.mark.asyncio
async def test_create_data_service_token_and_verify_payload_local_mode(fake_redis, tmp_path) -> None:
    security._redis_client = fake_redis
    security.settings.jwt_private_key_path = tmp_path / "private.pem"
    security.settings.jwt_public_key_path = tmp_path / "public.pem"
    security.settings.token_local_validation = True

    token = security.create_data_service_token({"sub": str(uuid4()), "hostname": "acq-pc-01"})
    payload, client = await security.verify_data_service_token_payload(token)

    assert payload["type"] == "data_service"
    assert payload["hostname"] == "acq-pc-01"
    assert client is None


@pytest.mark.asyncio
async def test_verify_data_service_token_payload_db_mode(db_session, fake_redis, tmp_path) -> None:
    security._redis_client = fake_redis
    security.settings.jwt_private_key_path = tmp_path / "private.pem"
    security.settings.jwt_public_key_path = tmp_path / "public.pem"
    security.settings.token_local_validation = False

    client = DataServiceClient(
        id=uuid4(),
        hostname="acq-pc-01",
        watch_folder="C:/watch",
        os_info="Windows 11",
        agent_version="0.1.0",
        api_key_hash=await security.hash_secret("api-key"),
        session_token_hash=None,
        session_expires_at=None,
        status=DataServiceClientStatus.NEVER_SEEN,
        is_revoked=False,
    )
    db_session.add(client)
    await db_session.commit()

    token = security.create_data_service_token({"sub": str(client.id), "hostname": client.hostname})
    client.session_token_hash = await security.hash_secret(token)
    client.session_expires_at = datetime.now(UTC) + timedelta(hours=8)
    await db_session.commit()

    payload, verified_client = await security.verify_data_service_token_payload(token, db_session=db_session)
    security.settings.token_local_validation = True

    assert payload.client_id == client.id
    assert verified_client is not None
    assert verified_client.id == client.id


@pytest.mark.asyncio
async def test_verify_data_service_token_payload_rejects_expired_session(
    db_session,
    fake_redis,
    tmp_path,
) -> None:
    security._redis_client = fake_redis
    security.settings.jwt_private_key_path = tmp_path / "private.pem"
    security.settings.jwt_public_key_path = tmp_path / "public.pem"
    security.settings.token_local_validation = False

    client = DataServiceClient(
        id=uuid4(),
        hostname="acq-pc-01",
        watch_folder="C:/watch",
        os_info="Windows 11",
        agent_version="0.1.0",
        api_key_hash=await security.hash_secret("api-key"),
        session_token_hash=None,
        session_expires_at=None,
        status=DataServiceClientStatus.NEVER_SEEN,
        is_revoked=False,
    )
    db_session.add(client)
    await db_session.commit()

    token = security.create_data_service_token({"sub": str(client.id), "hostname": client.hostname})
    client.session_token_hash = await security.hash_secret(token)
    client.session_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.commit()

    with pytest.raises(HTTPException, match="expired"):
        await security.verify_data_service_token_payload(token, db_session=db_session)

    security.settings.token_local_validation = True
