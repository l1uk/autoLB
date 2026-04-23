from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _base_settings_kwargs() -> dict[str, object]:
    return {
        "POSTGRES_DB": "autologbook",
        "POSTGRES_USER": "alb",
        "POSTGRES_PASSWORD": "alb_dev_password",
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "REDIS_URL": "redis://redis:6379/0",
        "MINIO_ENDPOINT": "minio:9000",
        "MINIO_ACCESS_KEY": "minioadmin",
        "MINIO_SECRET_KEY": "minioadmin",
        "MINIO_BUCKET": "autologbook-dev",
        "SECRET_KEY": "replace-with-a-long-random-secret",
        "REGISTRATION_SECRET": "super-secret-registration",
        "CONTEXT_ID_HMAC_KEY": "this-is-a-very-secret-hmac-key-with-32-plus-bytes",
    }


def test_missing_registration_secret_raises_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REGISTRATION_SECRET", raising=False)
    settings_kwargs = _base_settings_kwargs()
    settings_kwargs.pop("REGISTRATION_SECRET")

    with pytest.raises(ValidationError):
        Settings(_env_file=None, **settings_kwargs)


def test_missing_context_id_hmac_key_raises_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CONTEXT_ID_HMAC_KEY", raising=False)
    settings_kwargs = _base_settings_kwargs()
    settings_kwargs.pop("CONTEXT_ID_HMAC_KEY")

    with pytest.raises(ValidationError):
        Settings(_env_file=None, **settings_kwargs)
