from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_healthcheck_returns_ok(async_client: AsyncClient) -> None:
    response = await async_client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_healthcheck_rejects_invalid_method(async_client: AsyncClient) -> None:
    response = await async_client.post("/healthz")

    assert response.status_code == 405
