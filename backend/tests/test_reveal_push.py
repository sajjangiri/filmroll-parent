"""Guest reveal push.

The host already gets email when a film develops. Guests are holding a camera,
so a notification on that phone is the matching channel. Instant films never
send it: they are born developed, and "your film is ready" would land at create.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from httpx import AsyncClient

from app.db.sync_session import session_scope
from app.services import notify, push
from tests.conftest import auth, join, make_film

pytestmark = pytest.mark.integration

TOKEN = "ExponentPushToken[FilmrollTestToken0001]"
OTHER = "ExponentPushToken[FilmrollTestToken0002]"


async def test_a_guest_can_register_an_expo_token(
    client: AsyncClient, past: datetime, future: datetime
) -> None:
    code, _ = await make_film(client, closes_at=future, reveal_at=past)
    guest = await join(client, code, "Alice")
    response = await client.put(
        f"/v1/films/{code}/push-token",
        json={"token": TOKEN, "locale": "es"},
        headers=auth(guest),
    )
    assert response.status_code == 204, response.text

    push.outbox.clear()
    with session_scope() as session:
        assert notify.notify_developed_films(session) == 1
    assert len(push.outbox) == 1
    assert push.outbox[0].to == TOKEN
    assert push.outbox[0].code == code
    assert "revelado" in push.outbox[0].title

    with session_scope() as session:
        assert notify.notify_developed_films(session) == 0
    assert len(push.outbox) == 1


async def test_a_new_phone_overwrites_the_old_token(
    client: AsyncClient, past: datetime, future: datetime
) -> None:
    code, _ = await make_film(client, closes_at=future, reveal_at=past)
    guest = await join(client, code, "Alice")
    await client.put(
        f"/v1/films/{code}/push-token",
        json={"token": TOKEN},
        headers=auth(guest),
    )
    replaced = await client.put(
        f"/v1/films/{code}/push-token",
        json={"token": OTHER, "locale": "en"},
        headers=auth(guest),
    )
    assert replaced.status_code == 204

    push.outbox.clear()
    with session_scope() as session:
        notify.notify_developed_films(session)
    assert [item.to for item in push.outbox] == [OTHER]


async def test_guests_are_notified_even_without_a_host_email(
    client: AsyncClient, past: datetime, future: datetime
) -> None:
    code, _ = await make_film(client, closes_at=future, reveal_at=past)
    guest = await join(client, code, "Alice")
    await client.put(
        f"/v1/films/{code}/push-token",
        json={"token": TOKEN},
        headers=auth(guest),
    )

    push.outbox.clear()
    with session_scope() as session:
        assert notify.notify_developed_films(session) == 1
    assert push.outbox[0].to == TOKEN


async def test_a_host_token_cannot_register_a_guest_push_token(
    client: AsyncClient, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    response = await client.put(
        f"/v1/films/{code}/push-token",
        json={"token": TOKEN},
        headers=auth(host),
    )
    assert response.status_code == 403


async def test_a_non_expo_token_is_rejected(
    client: AsyncClient, future: datetime
) -> None:
    code, _ = await make_film(client, closes_at=future, reveal_at=future)
    guest = await join(client, code, "Alice")
    response = await client.put(
        f"/v1/films/{code}/push-token",
        json={"token": "https://evil.example/hook"},
        headers=auth(guest),
    )
    assert response.status_code == 422


async def test_an_instant_film_does_not_push_guests(client: AsyncClient, future: datetime) -> None:
    created = await client.post(
        "/v1/films",
        json={
            "title": "Live",
            "event_type": "party",
            "closes_at": future.isoformat(),
            "instant_reveal": True,
            "shot_limit": 8,
            "guest_cap": 5,
        },
    )
    assert created.status_code == 201, created.text
    code = created.json()["film"]["code"]
    guest = await join(client, code, "Alice")
    await client.put(
        f"/v1/films/{code}/push-token",
        json={"token": TOKEN},
        headers=auth(guest),
    )

    push.outbox.clear()
    with session_scope() as session:
        assert notify.notify_developed_films(session) == 0
    assert push.outbox == []


async def test_two_guests_each_get_their_own_push(
    client: AsyncClient, past: datetime, future: datetime
) -> None:
    code, _ = await make_film(client, closes_at=future, reveal_at=past)
    alice = await join(client, code, "Alice")
    bob = await join(client, code, "Bob")
    await client.put(
        f"/v1/films/{code}/push-token",
        json={"token": TOKEN},
        headers=auth(alice),
    )
    await client.put(
        f"/v1/films/{code}/push-token",
        json={"token": OTHER, "locale": "fr"},
        headers=auth(bob),
    )

    push.outbox.clear()
    with session_scope() as session:
        notify.notify_developed_films(session)
    targets = sorted(item.to for item in push.outbox)
    assert targets == sorted([TOKEN, OTHER])
    french = next(item for item in push.outbox if item.to == OTHER)
    assert "révélé" in french.title
