"""Test harness.

Tests run against the real Postgres, Redis and MinIO from docker compose, using
a dedicated database and bucket. Substituting SQLite would be actively
misleading here: cap enforcement is a raw conditional INSERT with FOR UPDATE
row locks, and the reveal predicate evaluates Postgres ``now()``. Neither exists
outside Postgres, so the behaviour under test would not be the behaviour that
ships.

Testcontainers was the original plan, but pytest executes inside the api
container, which has no Docker socket and therefore cannot start containers.
"""

from __future__ import annotations

import os

# Must precede any app import so cached settings pick up the test targets.
os.environ["DATABASE_URL"] = "postgresql+asyncpg://filmroll:filmroll@db:5432/filmroll_test"
os.environ["DATABASE_URL_SYNC"] = "postgresql+psycopg://filmroll:filmroll@db:5432/filmroll_test"
os.environ["S3_BUCKET"] = "filmroll-test"
os.environ["ENVIRONMENT"] = "ci"
# Tests reach storage over the compose network, so presigned URLs must be signed
# against that host. SigV4 covers the Host header, so rewriting the host after
# signing yields SignatureDoesNotMatch.
os.environ["S3_PUBLIC_ENDPOINT_URL"] = "http://minio:9000"
os.environ["SECRET_KEY"] = "test-secret-key-at-least-32-bytes-long-for-hmac-sha256"
# Small enough that the oversized-upload tests do not push 25 MB through MinIO.
os.environ["MAX_UPLOAD_BYTES"] = "65536"
os.environ["PUBLIC_WEB_URL"] = "http://localhost:3000"

import uuid  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402

import boto3  # noqa: E402
import psycopg  # noqa: E402
import pytest  # noqa: E402
from botocore.client import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import Base, dispose_engine, get_engine  # noqa: E402
from app.main import app  # noqa: E402

TEST_DB = "filmroll_test"


def _ensure_database() -> None:
    with psycopg.connect(
        "postgresql://filmroll:filmroll@db:5432/postgres", autocommit=True
    ) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')


def _ensure_bucket() -> None:
    settings = get_settings()
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    buckets = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
    if settings.s3_bucket not in buckets:
        client.create_bucket(Bucket=settings.s3_bucket)


@pytest.fixture(scope="session", autouse=True)
async def _schema() -> AsyncIterator[None]:
    _ensure_database()
    _ensure_bucket()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await dispose_engine()


@pytest.fixture(autouse=True)
async def _clean_tables() -> AsyncIterator[None]:
    """Truncate between tests.

    Real commits are required because the concurrency suites need one
    transaction to observe another's committed rows, so a rollback-per-test
    strategy would defeat the tests that matter most.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE films, guests, shots RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ------------------------------------------------------------------- factories


@pytest.fixture
def future() -> datetime:
    return datetime.now(UTC) + timedelta(hours=6)


@pytest.fixture
def past() -> datetime:
    return datetime.now(UTC) - timedelta(minutes=5)


async def make_film(
    client: AsyncClient,
    *,
    closes_at: datetime,
    reveal_at: datetime,
    shot_limit: int = 24,
    guest_cap: int = 25,
    title: str = "Test Film",
) -> tuple[str, str]:
    """Create a film, returning (code, host_token)."""
    response = await client.post(
        "/v1/films",
        json={
            "title": title,
            "event_type": "wedding",
            "closes_at": closes_at.isoformat(),
            "reveal_at": reveal_at.isoformat(),
            "shot_limit": shot_limit,
            "guest_cap": guest_cap,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["film"]["code"], body["host_token"]


async def join(client: AsyncClient, code: str, name: str = "Guest") -> str:
    """Join a film, returning the guest token."""
    response = await client.post(f"/v1/films/{code}/join", json={"display_name": name})
    assert response.status_code == 201, response.text
    return response.json()["guest_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# Structurally valid JPEG; storage does not care about pixel content.
TINY_JPEG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffd9")


async def upload_shot(
    client: AsyncClient, code: str, token: str, *, shot_id: str | None = None
) -> str:
    """Reserve, upload directly to storage, and commit. Returns the shot id."""
    import httpx

    shot_id = shot_id or str(uuid.uuid4())
    reserved = await client.post(
        f"/v1/films/{code}/shots/reserve",
        json={"shot_id": shot_id},
        headers=auth(token),
    )
    assert reserved.status_code == 200, reserved.text

    url = reserved.json()["upload_url"]
    async with httpx.AsyncClient() as raw:
        put = await raw.put(url, content=TINY_JPEG, headers={"Content-Type": "image/jpeg"})
        assert put.status_code == 200, put.text

    committed = await client.post(f"/v1/films/{code}/shots/{shot_id}/commit", headers=auth(token))
    assert committed.status_code == 200, committed.text
    return shot_id
