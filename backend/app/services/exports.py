"""Status for the originals ZIP. Redis, not Postgres.

The zip itself lives in object storage. This is only the "is it ready" bit, so
a host can poll without listing the bucket. Redis is not the source of truth:
if it is empty, we fall through to checking whether the object exists.
"""

from __future__ import annotations

import redis as redis_sync
import redis.asyncio as aioredis

from app.core.config import get_settings
from app.services import storage

PENDING = "pending"
READY = "ready"
FAILED = "failed"

_TTL_SECONDS = 24 * 60 * 60
_async: aioredis.Redis | None = None
_sync: redis_sync.Redis | None = None


def _redis_key(film_id: str) -> str:
    return f"export:{film_id}"


def _async_redis() -> aioredis.Redis:
    global _async
    if _async is None:
        _async = aioredis.from_url(  # type: ignore[no-untyped-call]
            get_settings().redis_url, decode_responses=True
        )
    return _async


def _sync_redis() -> redis_sync.Redis:
    global _sync
    if _sync is None:
        _sync = redis_sync.from_url(  # type: ignore[no-untyped-call]
            get_settings().redis_url, decode_responses=True
        )
    return _sync


async def mark_pending(film_id: str) -> None:
    try:
        await _async_redis().set(_redis_key(film_id), PENDING, ex=_TTL_SECONDS)
    except Exception:
        return


def mark_ready_sync(film_id: str) -> None:
    try:
        _sync_redis().set(_redis_key(film_id), READY, ex=_TTL_SECONDS)
    except Exception:
        return


def mark_failed_sync(film_id: str) -> None:
    try:
        _sync_redis().set(_redis_key(film_id), FAILED, ex=_TTL_SECONDS)
    except Exception:
        return


async def status(film_id: str) -> str:
    try:
        value = await _async_redis().get(_redis_key(film_id))
        if value in {PENDING, READY, FAILED}:
            return str(value)
    except Exception:
        pass
    exists = await storage.object_exists(storage.export_key(film_id, "originals"))
    return READY if exists else "idle"
