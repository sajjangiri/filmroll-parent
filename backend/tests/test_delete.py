"""Deleting a film.

Two properties matter here and they pull against each other. A host who deletes
an event must have it gone immediately, from guests and co-hosts alike. But the
photographs are usually the only copies in existence, so an accidental tap must
stay recoverable for a while. Hence: invisible now, destroyed later.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.db.models import Film, Guest, Payment, Shot
from app.db.session import get_sessionmaker
from app.services import storage
from tests.conftest import auth, invite_seat, join, make_film, upload_shot

pytestmark = pytest.mark.integration


async def _film_row(code: str) -> Film:
    async with get_sessionmaker()() as session:
        return (await session.execute(select(Film).where(Film.code == code))).scalar_one()


async def _age_the_deletion(code: str, *, days: int) -> None:
    """Backdate deleted_at so the purge sweep considers the film due."""
    async with get_sessionmaker()() as session:
        await session.execute(
            text("UPDATE films SET deleted_at = :when WHERE code = :code"),
            {"when": datetime.now(UTC) - timedelta(days=days), "code": code},
        )
        await session.commit()


async def test_delete_hides_the_film_from_everyone(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    guest = await join(client, code)

    deleted = await client.delete(f"/v1/films/{code}", headers=auth(host))
    assert deleted.status_code == 200, deleted.text
    body = deleted.json()
    assert body["code"] == code
    assert datetime.fromisoformat(body["purge_at"]) > datetime.now(UTC)

    # The public film, the gallery, and the guest's own session all stop.
    assert (await client.get(f"/v1/films/{code}")).status_code == 404
    assert (await client.get(f"/v1/films/{code}/gallery")).status_code == 404
    assert (
        await client.post(
            f"/v1/films/{code}/shots/reserve",
            json={"shot_id": "11111111-1111-1111-1111-111111111111"},
            headers=auth(guest),
        )
    ).status_code == 404
    assert (
        await client.post(f"/v1/films/{code}/join", json={"display_name": "Late"})
    ).status_code == 404
    assert (await client.get(f"/v1/films/{code}/review", headers=auth(host))).status_code == 404


async def test_delete_is_idempotent(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    first = await client.delete(f"/v1/films/{code}", headers=auth(host))
    # The second call cannot reach the film at all, which is the correct answer
    # for a caller retrying a request whose response they never saw.
    second = await client.delete(f"/v1/films/{code}", headers=auth(host))
    assert first.status_code == 200
    assert second.status_code == 404


async def test_bytes_survive_the_grace_period(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    guest = await join(client, code)
    shot_id = await upload_shot(client, code, guest)

    await client.delete(f"/v1/films/{code}", headers=auth(host))

    film = await _film_row(code)
    assert film.deleted_at is not None
    assert film.purged_at is None
    assert storage.object_exists_sync(storage.original_key(str(film.id), shot_id))


async def test_restore_brings_the_film_back(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    guest = await join(client, code)
    shot_id = await upload_shot(client, code, guest)
    await client.delete(f"/v1/films/{code}", headers=auth(host))

    restored = await client.post(f"/v1/films/{code}/restore", headers=auth(host))
    assert restored.status_code == 200, restored.text
    assert restored.json()["code"] == code

    assert (await client.get(f"/v1/films/{code}")).status_code == 200
    review = await client.get(f"/v1/films/{code}/review", headers=auth(host))
    assert [photo["shot_id"] for photo in review.json()["photos"]] == [shot_id]


async def test_only_the_owner_can_delete_or_restore(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    guest = await join(client, code)
    _, cohost = await invite_seat(client, code, host, role="cohost")

    # A co-host can run the whole event but cannot end it.
    assert (await client.delete(f"/v1/films/{code}", headers=auth(cohost))).status_code == 403
    assert (await client.delete(f"/v1/films/{code}", headers=auth(guest))).status_code == 403

    await client.delete(f"/v1/films/{code}", headers=auth(host))
    # A deleted film must not confirm its own existence to the wrong token.
    assert (await client.post(f"/v1/films/{code}/restore", headers=auth(cohost))).status_code == 404
    assert (await client.post(f"/v1/films/{code}/restore", headers=auth(guest))).status_code == 404


async def test_a_host_token_cannot_restore_another_film(
    client: AsyncClient, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    other, other_host = await make_film(client, closes_at=future, reveal_at=future, title="Other")
    await client.delete(f"/v1/films/{code}", headers=auth(host))

    stolen = await client.post(f"/v1/films/{code}/restore", headers=auth(other_host))
    assert stolen.status_code == 404
    # Still deleted, and still restorable by the right token.
    assert (await client.post(f"/v1/films/{code}/restore", headers=auth(host))).status_code == 200
    assert other


async def test_restoring_a_film_that_was_never_deleted_is_a_no_op(
    client: AsyncClient, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    response = await client.post(f"/v1/films/{code}/restore", headers=auth(host))
    assert response.status_code == 200
    assert (await client.get(f"/v1/films/{code}")).status_code == 200


async def test_purge_destroys_photos_but_keeps_the_receipts(
    client: AsyncClient, future: datetime
) -> None:
    from app.worker.tasks import purge_deleted_films

    code, host = await make_film(client, closes_at=future, reveal_at=future, guest_cap=50)
    guest = await join(client, code)
    shot_id = await upload_shot(client, code, guest)
    film = await _film_row(code)
    key = storage.original_key(str(film.id), shot_id)
    assert storage.object_exists_sync(key)

    await client.delete(f"/v1/films/{code}", headers=auth(host))
    await _age_the_deletion(code, days=31)

    assert purge_deleted_films() == 1

    # The photographs are gone, along with the guest list that named them.
    assert not storage.object_exists_sync(key)
    async with get_sessionmaker()() as session:
        shots = (await session.execute(select(Shot).where(Shot.film_id == film.id))).scalars().all()
        guests = (
            (await session.execute(select(Guest).where(Guest.film_id == film.id))).scalars().all()
        )
        payments = (
            (await session.execute(select(Payment).where(Payment.film_id == film.id)))
            .scalars()
            .all()
        )
    assert shots == []
    assert guests == []
    # The upgrade to 50 guests was a real sale and stays on the books.
    assert len(payments) == 1

    purged = await _film_row(code)
    assert purged.purged_at is not None


async def test_purge_leaves_films_inside_the_grace_window_alone(
    client: AsyncClient, future: datetime
) -> None:
    from app.worker.tasks import purge_deleted_films

    code, host = await make_film(client, closes_at=future, reveal_at=future)
    guest = await join(client, code)
    shot_id = await upload_shot(client, code, guest)
    await client.delete(f"/v1/films/{code}", headers=auth(host))
    await _age_the_deletion(code, days=29)

    assert purge_deleted_films() == 0

    film = await _film_row(code)
    assert film.purged_at is None
    assert storage.object_exists_sync(storage.original_key(str(film.id), shot_id))


async def test_purge_ignores_live_films(client: AsyncClient, future: datetime) -> None:
    from app.worker.tasks import purge_deleted_films

    code, _ = await make_film(client, closes_at=future, reveal_at=future)
    assert purge_deleted_films() == 0
    assert (await client.get(f"/v1/films/{code}")).status_code == 200


async def test_a_purged_film_cannot_be_restored(client: AsyncClient, future: datetime) -> None:
    from app.worker.tasks import purge_deleted_films

    code, host = await make_film(client, closes_at=future, reveal_at=future)
    await client.delete(f"/v1/films/{code}", headers=auth(host))
    await _age_the_deletion(code, days=31)
    purge_deleted_films()

    response = await client.post(f"/v1/films/{code}/restore", headers=auth(host))
    assert response.status_code == 410


async def test_the_code_is_not_reused_by_a_deleted_film(
    client: AsyncClient, future: datetime
) -> None:
    """The row is kept, so its unique code stays taken.

    A restored film has to be reachable at the address on the printed cards.
    """
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    await client.delete(f"/v1/films/{code}", headers=auth(host))

    fresh, _ = await make_film(client, closes_at=future, reveal_at=future, title="New")
    assert fresh != code
