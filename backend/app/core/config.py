from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["local", "ci", "staging", "production"] = "local"
    log_level: str = "INFO"
    secret_key: str = "dev-only-insecure-key-change-me"

    # Kept as a raw string rather than list[str]. pydantic-settings JSON-decodes
    # complex types inside the env source, which happens before any validator
    # runs, so a comma-separated value raises SettingsError instead of reaching
    # the validator. Parsing happens in cors_origin_list below.
    cors_origins: str = ""

    database_url: str = "postgresql+asyncpg://filmroll:filmroll@db:5432/filmroll"
    database_url_sync: str = "postgresql+psycopg://filmroll:filmroll@db:5432/filmroll"

    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # Internal endpoint is used by the API and workers over the container
    # network. The public one is what presigned URLs are signed against, because
    # a phone browser cannot resolve a compose service name.
    s3_endpoint_url: str = "http://minio:9000"
    s3_public_endpoint_url: str = "http://localhost:9000"
    s3_access_key_id: str = "filmroll"
    s3_secret_access_key: str = "filmroll-dev-secret"
    s3_bucket: str = "filmroll-shots"
    s3_region: str = "us-east-1"
    s3_force_path_style: bool = True

    upload_url_ttl_seconds: int = 900
    download_url_ttl_seconds: int = 300
    reservation_ttl_minutes: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
