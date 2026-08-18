"""Caps under concurrency, and idempotency under retries.

The caps are the pricing tiers, so a race here leaks revenue. The idempotency
cases model venue wifi, where clients retry aggressively and the same request
arrives many times.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.db.models import Shot
from app.db.session import get_sessionmaker
from app.main import app
from tests.conftest import auth, join, make_film, upload_shot

pytestmark = pytest.mark.integration


def _fresh_client() -> AsyncClient:
    """Independent client so requests do not serialise on one connection."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.concurrency
async def test_shot_cap_holds_under_parallel_reservations(client: AsyncClient, future):
    """Twenty simultaneous reservations against a five-shot roll.

    The conditional INSERT alone cannot do this: under READ COMMITTED the count
    subquery takes no lock, so every caller would observe four used shots and
    all twenty would succeed. Serialising on the guest row is what holds the
    line.
    """
    code, _ = await make_film(client, closes_at=future, reveal_at=future, shot_limit=5)
    token = await join(client, code)

    async def reserve() -> int:
        async with _fresh_client() as c:
            response = await c.post(
                f"/v1/films/{code}/shots/reserve",
                json={"shot_id": str(uuid.uuid4())},
                headers=auth(token),
            )
            return response.status_code

    results = await asyncio.gather(*(reserve() for _ in range(20)))

    assert results.count(200) == 5
    assert results.count(409) == 15

    async with get_sessionmaker()() as session:
        rows = await session.scalar(select(func.count()).select_from(Shot))
    assert rows == 5


@pytest.mark.concurrency
async def test_guest_cap_holds_under_parallel_joins(client: AsyncClient, future):
    code, _ = await make_film(client, closes_at=future, reveal_at=future, guest_cap=4)

    async def join_once(n: int) -> int:
        async with _fresh_client() as c:
            response = await c.post(
                f"/v1/films/{code}/join", json={"display_name": f"G{n}"}
            )
            return response.status_code

    results = await asyncio.gather(*(join_once(n) for n in range(20)))

    assert results.count(201) == 4
    assert results.count(409) == 16


@pytest.mark.concurrency
async def test_replayed_shot_id_creates_exactly_one_row(client: AsyncClient, future):
    """The same reservation sent ten times over must not burn ten slots."""
    code, _ = await make_film(client, closes_at=future, reveal_at=future, shot_limit=10)
    token = await join(client, code)
    shot_id = str(uuid.uuid4())

    async def reserve() -> int:
        async with _fresh_client() as c:
            response = await c.post(
                f"/v1/films/{code}/shots/reserve",
                json={"shot_id": shot_id},
                headers=auth(token),
            )
            return response.status_code

    results = await asyncio.gather(*(reserve() for _ in range(10)))
    assert all(status == 200 for status in results)

    async with get_sessionmaker()() as session:
        rows = await session.scalar(select(func.count()).select_from(Shot))
    assert rows == 1


async def test_replay_reports_already_reserved_without_consuming_a_slot(
    client: AsyncClient, future
):
    code, _ = await make_film(client, closes_at=future, reveal_at=future, shot_limit=3)
    token = await join(client, code)
    shot_id = str(uuid.uuid4())

    first = await client.post(
        f"/v1/films/{code}/shots/reserve",
        json={"shot_id": shot_id},
        headers=auth(token),
    )
    second = await client.post(
        f"/v1/films/{code}/shots/reserve",
        json={"shot_id": shot_id},
        headers=auth(token),
    )

    assert first.json()["already_reserved"] is False
    assert second.json()["already_reserved"] is True
    assert first.json()["shots_remaining"] == second.json()["shots_remaining"] == 2


async def test_commit_without_an_upload_is_refused(client: AsyncClient, future):
    """Trusting the client here would put a broken image in the gallery."""
    code, _ = await make_film(client, closes_at=future, reveal_at=future)
    token = await join(client, code)
    shot_id = str(uuid.uuid4())

    await client.post(
        f"/v1/films/{code}/shots/reserve",
        json={"shot_id": shot_id},
        headers=auth(token),
    )
    response = await client.post(
        f"/v1/films/{code}/shots/{shot_id}/commit", headers=auth(token)
    )
    assert response.status_code == 409


async def test_committing_twice_is_idempotent(client: AsyncClient, future):
    code, _ = await make_film(client, closes_at=future, reveal_at=future)
    token = await join(client, code)
    shot_id = await upload_shot(client, code, token)

    again = await client.post(
        f"/v1/films/{code}/shots/{shot_id}/commit", headers=auth(token)
    )
    assert again.status_code == 200
    assert again.json()["state"] == "uploaded"


async def test_reserved_shots_count_against_the_cap(client: AsyncClient, future):
    """Otherwise a guest could dodge the limit by abandoning reservations."""
    code, _ = await make_film(client, closes_at=future, reveal_at=future, shot_limit=2)
    token = await join(client, code)

    for _ in range(2):
        assert (
            await client.post(
                f"/v1/films/{code}/shots/reserve",
                json={"shot_id": str(uuid.uuid4())},
                headers=auth(token),
            )
        ).status_code == 200

    blocked = await client.post(
        f"/v1/films/{code}/shots/reserve",
        json={"shot_id": str(uuid.uuid4())},
        headers=auth(token),
    )
    assert blocked.status_code == 409


async def test_closed_film_accepts_nothing_further(client: AsyncClient, past):
    code, _ = await make_film(client, closes_at=past, reveal_at=past)

    joined = await client.post(f"/v1/films/{code}/join", json={"display_name": "Late"})
    assert joined.status_code == 410


async def test_cap_raised_mid_event_unblocks_the_guest(client: AsyncClient, future):
    """Hosts upgrade during an event; the new limit must apply immediately."""
    code, _ = await make_film(client, closes_at=future, reveal_at=future, shot_limit=1)
    token = await join(client, code)

    await client.post(
        f"/v1/films/{code}/shots/reserve",
        json={"shot_id": str(uuid.uuid4())},
        headers=auth(token),
    )
    blocked = await client.post(
        f"/v1/films/{code}/shots/reserve",
        json={"shot_id": str(uuid.uuid4())},
        headers=auth(token),
    )
    assert blocked.status_code == 409

    async with get_sessionmaker()() as session:
        from sqlalchemy import update

        from app.db.models import Film

        await session.execute(update(Film).where(Film.code == code).values(shot_limit=3))
        await session.commit()

    allowed = await client.post(
        f"/v1/films/{code}/shots/reserve",
        json={"shot_id": str(uuid.uuid4())},
        headers=auth(token),
    )
    assert allowed.status_code == 200
