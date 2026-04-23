from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
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
    environment: str = Field(default="development", alias="ENVIRONMENT")
    REGISTRATION_SECRET: str = Field(
        ...,
        description="Pre-shared secret for data-service registration (SRS SEC-1). Must match the value provided to the data-service installer out-of-band.",
    )
    CONTEXT_ID_HMAC_KEY: str = Field(
        ...,
        description="HMAC-SHA256 key for context_id generation and verification (SRS SEC-3). Must be at least 32 bytes of entropy. Never commit to version control.",
    )
    DATA_SERVICE_CURRENT_VERSION: str = Field(
        default="0.1.0",
        description="Current authoritative version string for GET /data-service/version (RF-24 stub)",
    )
    TOKEN_LOCAL_VALIDATION: bool = Field(
        default=True,
        description="If True, validate data-service JWT locally only. If False, also check DB session record (\u00a78.1).",
    )
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

    @property
    def registration_token(self) -> str:
        return self.REGISTRATION_SECRET

    @registration_token.setter
    def registration_token(self, value: str) -> None:
        self.REGISTRATION_SECRET = value

    @property
    def token_local_validation(self) -> bool:
        return self.TOKEN_LOCAL_VALIDATION

    @token_local_validation.setter
    def token_local_validation(self, value: bool) -> None:
        self.TOKEN_LOCAL_VALIDATION = value

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.environment.lower() != "production":
            return self

        invalid_fields: list[str] = []
        if self.REGISTRATION_SECRET == "change-me-before-deployment":
            invalid_fields.append("REGISTRATION_SECRET")
        if self.CONTEXT_ID_HMAC_KEY == "change-me-before-deployment":
            invalid_fields.append("CONTEXT_ID_HMAC_KEY")

        if invalid_fields:
            raise ValueError(
                "Invalid production configuration: "
                f"{', '.join(invalid_fields)} uses placeholder value 'change-me-before-deployment'. "
                "Set secure non-default values before startup."
            )

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
