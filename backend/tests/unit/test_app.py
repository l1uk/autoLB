from __future__ import annotations


async def test_healthcheck(async_client) -> None:
    response = await async_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
