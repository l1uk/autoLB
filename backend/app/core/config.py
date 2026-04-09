from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_db: str = Field(alias="POSTGRES_DB")
    postgres_user: str = Field(alias="POSTGRES_USER")
    postgres_password: str = Field(alias="POSTGRES_PASSWORD")
    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")
    minio_endpoint: str = Field(alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(alias="MINIO_SECRET_KEY")
    minio_bucket: str = Field(alias="MINIO_BUCKET")
    secret_key: str = Field(alias="SECRET_KEY")
    jwt_algorithm: str = Field(default="RS256", alias="JWT_ALGORITHM")
    access_token_ttl_minutes: int = Field(default=15, alias="ACCESS_TOKEN_TTL_MINUTES")
    refresh_token_ttl_days: int = Field(default=7, alias="REFRESH_TOKEN_TTL_DAYS")
    data_service_token_ttl_hours: int = Field(default=8, alias="DATA_SERVICE_TOKEN_TTL_HOURS")
    heartbeat_interval_seconds: int = Field(default=30, alias="HEARTBEAT_INTERVAL_SECONDS")
    jwt_private_key_path: Path = Field(
        default=Path("/tmp/autologbook/jwt_private.pem"),
        alias="JWT_PRIVATE_KEY_PATH",
    )
    jwt_public_key_path: Path = Field(
        default=Path("/tmp/autologbook/jwt_public.pem"),
        alias="JWT_PUBLIC_KEY_PATH",
    )
    cors_allowed_origins: list[str] = Field(default_factory=lambda: ["*"], alias="CORS_ALLOWED_ORIGINS")
    token_local_validation: bool = Field(default=True, alias="TOKEN_LOCAL_VALIDATION")


@lru_cache
def get_settings() -> Settings:
    return Settings()
