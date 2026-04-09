from __future__ import annotations

from app.worker import create_celery_app


def test_create_celery_app_uses_default_redis_url(monkeypatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)

    celery_app = create_celery_app()

    assert celery_app.conf.broker_url == "redis://redis:6379/0"
    assert celery_app.conf.result_backend == "redis://redis:6379/0"


def test_create_celery_app_uses_configured_redis_url(monkeypatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6380/2")

    celery_app = create_celery_app()

    assert celery_app.conf.broker_url == "redis://localhost:6380/2"
    assert celery_app.conf.result_backend == "redis://localhost:6380/2"
