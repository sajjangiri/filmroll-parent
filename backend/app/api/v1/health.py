import asyncio
from typing import Literal

import redis.asyncio as aioredis
from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_sessionmaker
from app.services import storage

router = APIRouter(tags=["health"])
log = get_logger(__name__)

ComponentState = Literal["ok", "down"]
OverallState = Literal["ok", "degraded", "down"]


class Health(BaseModel):
    status: OverallState
    database: ComponentState
    redis: ComponentState
    storage: ComponentState


async def _check_database() -> ComponentState:
    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        log.warning("health.database_unreachable", error=str(exc))
        return "down"
    return "ok"


async def _check_redis() -> ComponentState:
    # redis-py's from_url is untyped, which strict mode flags in a typed caller.
    client = aioredis.from_url(get_settings().redis_url)  # type: ignore[no-untyped-call]
    try:
        await client.ping()
    except Exception as exc:
        log.warning("health.redis_unreachable", error=str(exc))
        return "down"
    finally:
        await client.aclose()
    return "ok"


async def _check_storage() -> ComponentState:
    try:
        return "ok" if await storage.bucket_ready() else "down"
    except Exception as exc:
        log.warning("health.storage_unreachable", error=str(exc))
        return "down"


@router.get("/healthz", response_model=Health)
async def healthz(response: Response) -> Health:
    """Readiness for the whole stack.

    Postgres is the only hard dependency: without it no request can be served,
    so the endpoint fails outright. Redis and storage being down degrades the
    service (uploads and background work stop) but the API can still answer, so
    those report ``degraded`` rather than taking the container out of rotation.
    """
    database, redis_state, storage_state = await asyncio.gather(
        _check_database(), _check_redis(), _check_storage()
    )

    if database == "down":
        overall: OverallState = "down"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif "down" in (redis_state, storage_state):
        overall = "degraded"
    else:
        overall = "ok"

    return Health(
        status=overall,
        database=database,
        redis=redis_state,
        storage=storage_state,
    )
