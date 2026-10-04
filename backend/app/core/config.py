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

    # A deleted film disappears immediately but its bytes are kept this long, so
    # a mistap on the one copy of somebody's wedding is recoverable. Nothing in
    # the product surfaces a deleted film during the window.
    deleted_film_grace_days: int = 30

    # Where guests land when they scan a QR code. The API builds the join URL
    # itself so printed cards and the mobile app cannot disagree about it.
    public_web_url: str = "http://localhost:3000"

    # A presigned PUT is a capability: it names the key and the content type but
    # cannot bound the body. Storage is billed by the byte, so the size is
    # checked after the fact, on commit.
    max_upload_bytes: int = 25 * 1024 * 1024
    allowed_upload_types: str = "image/jpeg,image/png,image/webp,image/heic"
    # A 15 s phone clip at 1080p is ~30 MB; the headroom covers 4K phones. The
    # worker trims to the clip limit anyway, so this only bounds storage abuse.
    max_clip_bytes: int = 120 * 1024 * 1024
    allowed_clip_types: str = "video/mp4,video/quicktime,video/webm"

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
    # Catalog prices are what the host expects to pay, so tax is added on top by
    # default. Sell VAT-inclusive in the EU by flipping this to "inclusive".
    stripe_tax_behavior: str = "exclusive"
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

    # Expo's push gateway. Empty means messages land in ``app.services.push.outbox``
    # instead of opening a socket — the same trick mail uses in tests.
    expo_push_url: str = ""

    # Used to mint the Apple associated-domain file. TEAMID is a placeholder
    # until App Store Connect exists; the route still has to be served so a
    # CDN in front of us cannot 404 the well-known path.
    apple_team_id: str = ""
    ios_bundle_id: str = "app.filmroll"
    ios_clip_bundle_id: str = "app.filmroll.Clip"

    # Android App Links. Comma-separated SHA-256 fingerprints of the signing
    # certificates (debug keystore, upload key, Play app signing). Empty serves
    # an empty list: links still open the PWA, they just do not jump into the app.
    android_package: str = "app.filmroll"
    android_cert_sha256: str = ""

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
    def allowed_clip_type_set(self) -> frozenset[str]:
        return frozenset(
            item.strip().lower() for item in self.allowed_clip_types.split(",") if item.strip()
        )

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
