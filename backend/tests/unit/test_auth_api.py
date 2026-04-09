from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.security import hash_password
from app.domain.enums import UserRole
from app.domain.models import User


async def create_user(db_session, *, username: str = "alice", password: str = "secret123") -> User:
    user = User(
        id=uuid4(),
        email=f"{username}@example.com",
        username=username,
        role=UserRole.SYSTEM_ADMIN,
        hashed_password=hash_password(password),
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_login_happy_path(async_client, db_session) -> None:
    await create_user(db_session)

    response = await async_client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "secret123"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["refresh_token"]


@pytest.mark.asyncio
async def test_login_invalid_password(async_client, db_session) -> None:
    await create_user(db_session)

    response = await async_client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"


@pytest.mark.asyncio
async def test_refresh_happy_path(async_client, db_session) -> None:
    await create_user(db_session)
    login_response = await async_client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "secret123"},
    )
    refresh_token = login_response.json()["refresh_token"]

    response = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 200
    assert response.json()["refresh_token"] != refresh_token


@pytest.mark.asyncio
async def test_refresh_rejects_reused_token(async_client, db_session) -> None:
    await create_user(db_session)
    login_response = await async_client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "secret123"},
    )
    refresh_token = login_response.json()["refresh_token"]

    first_refresh = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    second_refresh = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert first_refresh.status_code == 200
    assert second_refresh.status_code == 401


@pytest.mark.asyncio
async def test_logout_happy_path(async_client, db_session) -> None:
    await create_user(db_session)
    login_response = await async_client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "secret123"},
    )
    refresh_token = login_response.json()["refresh_token"]

    response = await async_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_logout_rejects_invalid_token(async_client) -> None:
    response = await async_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": "not-a-jwt"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_happy_path(async_client, db_session) -> None:
    user = await create_user(db_session)
    login_response = await async_client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "secret123"},
    )
    access_token = login_response.json()["access_token"]

    response = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(user.id)
    assert response.json()["username"] == "alice"


@pytest.mark.asyncio
async def test_me_requires_valid_token(async_client) -> None:
    response = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
