"""Fixed-window rate limiting backed by Redis.

Deliberately simple. A sliding window or token bucket would be smoother, but
this runs on the join and reserve paths where the goal is only to stop a script
from exhausting a film. A real guest at an event never approaches these numbers.

Redis rather than in-process counters because the API is meant to scale
horizontally, and a per-process limit multiplies by the replica count.
"""

from __future__ import annotations

import time

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

_client: aioredis.Redis | None = None


def _redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(  # type: ignore[no-untyped-call]
            get_settings().redis_url, decode_responses=True
        )
    return _client


async def allow(bucket: str, identity: str, *, limit: int, window_seconds: int) -> bool:
    """Consume one unit. False means the caller is over its limit.

    Fails open. Redis is not the source of truth for anything here, and a limiter
    outage that blocked every guest at a wedding would be far worse than the
    burst it was meant to prevent.
    """
    window = int(time.time()) // window_seconds
    key = f"ratelimit:{bucket}:{identity}:{window}"

    try:
        pipe = _redis().pipeline()
        pipe.incr(key)
        # Set on every call rather than only the first. A TTL that fails to
        # apply would leave the key immortal and lock the identity out for good.
        pipe.expire(key, window_seconds)
        count, _ = await pipe.execute()
    except Exception as exc:
        log.warning("ratelimit.unavailable", bucket=bucket, error=str(exc))
        return True

    if int(count) > limit:
        log.info("ratelimit.blocked", bucket=bucket, identity=identity, count=int(count))
        return False
    return True


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
