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

    # Where guests land when they scan a QR code. The API builds the join URL
    # itself so printed cards and the mobile app cannot disagree about it.
    public_web_url: str = "http://localhost:3000"

    # A presigned PUT is a capability: it names the key and the content type but
    # cannot bound the body. Storage is billed by the byte, so the size is
    # checked after the fact, on commit.
    max_upload_bytes: int = 25 * 1024 * 1024
    allowed_upload_types: str = "image/jpeg,image/png,image/webp,image/heic"

    # Fixed-window limits. Generous enough that a real guest at an event never
    # notices, tight enough that a script cannot exhaust a film.
    rate_limit_join_per_hour: int = 20
    rate_limit_reserve_per_minute: int = 30

    # Billing. The catalog lives in code; these credentials only talk to Stripe.
    # Local development defaults to fake Checkout so a host can raise a cap
    # without an API key. Production refuses the fake path even if asked.
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_automatic_tax: bool = False
    billing_fake: bool = True

    # Local default is Mailpit on the compose network. Empty host means the
    # mailer records messages in-process (tests) instead of opening a socket.
    smtp_host: str = ""
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Filmroll <noreply@localhost>"
    smtp_starttls: bool = False

    rate_limit_recover_per_hour: int = 8

    @property
    def use_fake_billing(self) -> bool:
        if self.is_production:
            return False
        return self.billing_fake or not self.stripe_secret_key

    @property
    def stripe_configured(self) -> bool:
        return bool(self.stripe_secret_key)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def allowed_upload_type_set(self) -> frozenset[str]:
        return frozenset(
            item.strip().lower() for item in self.allowed_upload_types.split(",") if item.strip()
        )

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
