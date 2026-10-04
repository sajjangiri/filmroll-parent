"""Host email recovery, reveal notices, retention warnings, unlimited shots."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.models import Film
from app.db.session import get_sessionmaker
from app.db.sync_session import session_scope
from app.services import mail, notify
from tests.conftest import auth, join, make_film

pytestmark = pytest.mark.integration


def _magic_token() -> str:
    assert mail.outbox, "expected a captured email"
    body = mail.outbox[-1].body
    marker = "magic="
    assert marker in body, body
    return body.split(marker, 1)[1].split()[0]


async def test_public_film_payload_does_not_include_the_host_email(
    client: AsyncClient, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future, guest_cap=5)
    await client.patch(
        f"/v1/films/{code}",
        json={"host_email": "maya@example.com"},
        headers=auth(host),
    )
    public = (await client.get(f"/v1/films/{code}")).json()
    assert "host_email" not in public
    assert public["unlimited_shots"] is False

    account = await client.get(f"/v1/films/{code}/host/account", headers=auth(host))
    assert account.status_code == 200
    assert account.json()["email"] == "maya@example.com"

    guest = await join(client, code)
    denied = await client.get(f"/v1/films/{code}/host/account", headers=auth(guest))
    assert denied.status_code == 403


async def test_magic_link_restores_the_host_key(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future, guest_cap=5)
    saved = await client.patch(
        f"/v1/films/{code}",
        json={"host_email": "maya@example.com"},
        headers=auth(host),
    )
    assert saved.status_code == 200, saved.text
    assert mail.outbox
    assert mail.outbox[-1].to == "maya@example.com"

    wrong = await client.post(
        f"/v1/films/{code}/host/recover", json={"email": "stranger@example.com"}
    )
    assert wrong.status_code == 204
    assert len(mail.outbox) == 1

    recover = await client.post(
        f"/v1/films/{code}/host/recover", json={"email": "Maya@example.com"}
    )
    assert recover.status_code == 204
    token = _magic_token()

    session = await client.post(f"/v1/films/{code}/host/session", json={"magic_token": token})
    assert session.status_code == 200, session.text
    new_host = session.json()["host_token"]
    inbox = await client.get(f"/v1/films/{code}/review", headers=auth(new_host))
    assert inbox.status_code == 200


async def test_magic_link_for_the_wrong_film_is_rejected(
    client: AsyncClient, future: datetime
) -> None:
    first, host_a = await make_film(
        client, closes_at=future, reveal_at=future, guest_cap=5, title="A"
    )
    second, _ = await make_film(client, closes_at=future, reveal_at=future, guest_cap=5, title="B")
    await client.patch(
        f"/v1/films/{first}",
        json={"host_email": "maya@example.com"},
        headers=auth(host_a),
    )
    token = _magic_token()
    stolen = await client.post(f"/v1/films/{second}/host/session", json={"magic_token": token})
    assert stolen.status_code == 401


async def test_unlimited_shots_add_on_lifts_the_roll_limit(
    client: AsyncClient, future: datetime
) -> None:
    code, host = await make_film(
        client, closes_at=future, reveal_at=future, shot_limit=2, guest_cap=5
    )
    paid = await client.post(
        f"/v1/films/{code}/checkout",
        json={"addon_id": "unlimited_shots"},
        headers=auth(host),
    )
    assert paid.status_code == 200, paid.text
    film = (await client.get(f"/v1/films/{code}")).json()
    assert film["unlimited_shots"] is True

    guest = await join(client, code)
    import uuid

    statuses = []
    for _ in range(6):
        reserved = await client.post(
            f"/v1/films/{code}/shots/reserve",
            json={"shot_id": str(uuid.uuid4())},
            headers=auth(guest),
        )
        statuses.append(reserved.status_code)
    assert statuses.count(200) == 6
    assert 409 not in statuses


async def test_developed_film_notifies_the_host_once(client: AsyncClient, past: datetime) -> None:
    closes = datetime.now(UTC) + timedelta(hours=1)
    code, host = await make_film(client, closes_at=closes, reveal_at=past, guest_cap=5)
    await client.patch(
        f"/v1/films/{code}",
        json={"host_email": "maya@example.com"},
        headers=auth(host),
    )
    mail.outbox.clear()

    with session_scope() as session:
        sent = notify.notify_developed_films(session)
    assert sent == 1
    assert "has developed" in mail.outbox[-1].subject
    assert "/gallery" in mail.outbox[-1].body

    with session_scope() as session:
        assert notify.notify_developed_films(session) == 0


async def test_an_instant_film_does_not_get_a_developed_email(
    client: AsyncClient, future: datetime
) -> None:
    """A live film is born developed. 'Your film is ready' would land at create."""
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
    host = created.json()["host_token"]
    await client.patch(
        f"/v1/films/{code}",
        json={"host_email": "maya@example.com"},
        headers=auth(host),
    )
    mail.outbox.clear()

    with session_scope() as session:
        assert notify.notify_developed_films(session) == 0
    assert mail.outbox == []


async def test_retention_warning_fires_inside_the_30_day_window(
    client: AsyncClient, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future, guest_cap=5)
    await client.patch(
        f"/v1/films/{code}",
        json={"host_email": "maya@example.com"},
        headers=auth(host),
    )
    mail.outbox.clear()

    async with get_sessionmaker()() as session:
        film = await session.scalar(select(Film).where(Film.code == code.upper()))
        assert film is not None
        film.storage_until = datetime.now(UTC) + timedelta(days=20)
        await session.commit()

    with session_scope() as session:
        sent = notify.notify_retention_films(session)
    assert sent == 1
    assert "will be removed" in mail.outbox[-1].subject

    with session_scope() as session:
        assert notify.notify_retention_films(session) == 0
