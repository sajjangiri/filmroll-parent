"""Co-host and photographer seats.

The point of these tests is the permission boundary, not the CRUD. A co-host
must be able to run the event; a photographer must be able to pull originals
without being able to develop the film early or resize the room; and revoking
either has to bite on the very next request, not when the JWT expires.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from httpx import AsyncClient

from app.services.seats import MAX_ACTIVE_SEATS
from tests.conftest import auth, invite_seat, join, make_film, upload_shot

pytestmark = pytest.mark.integration


async def test_owner_can_invite_and_list_seats(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)

    created = await client.post(
        f"/v1/films/{code}/seats",
        json={"role": "cohost", "label": "Sam"},
        headers=auth(host),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["seat"]["role"] == "cohost"
    assert body["seat"]["label"] == "Sam"
    assert body["seat"]["claimed_at"] is None
    # The link is what the owner texts; it must name this film.
    assert f"/f/{code}/host?seat=" in body["invite_url"]

    listed = await client.get(f"/v1/films/{code}/seats", headers=auth(host))
    assert listed.status_code == 200
    assert [seat["label"] for seat in listed.json()["seats"]] == ["Sam"]


async def test_claiming_an_invite_stamps_the_seat(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    seat_id, token = await invite_seat(client, code, host, role="cohost", label="Sam")
    assert token

    listed = await client.get(f"/v1/films/{code}/seats", headers=auth(host))
    seat = next(row for row in listed.json()["seats"] if row["id"] == seat_id)
    assert seat["claimed_at"] is not None


async def test_cohost_can_moderate_and_reveal(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    guest = await join(client, code)
    shot_id = await upload_shot(client, code, guest)
    _, cohost = await invite_seat(client, code, host, role="cohost")

    hidden = await client.post(f"/v1/films/{code}/shots/{shot_id}/hide", headers=auth(cohost))
    assert hidden.status_code == 204

    capped = await client.patch(f"/v1/films/{code}", json={"shot_limit": 4}, headers=auth(cohost))
    assert capped.status_code == 200

    revealed = await client.post(f"/v1/films/{code}/reveal", headers=auth(cohost))
    assert revealed.status_code == 200
    assert revealed.json()["is_developed"] is True


async def test_photographer_can_read_but_not_change(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    guest = await join(client, code)
    shot_id = await upload_shot(client, code, guest)
    _, shooter = await invite_seat(client, code, host, role="photographer")

    # The whole reason the seat exists: see the shots, take the originals.
    review = await client.get(f"/v1/films/{code}/review", headers=auth(shooter))
    assert review.status_code == 200
    assert len(review.json()["photos"]) == 1

    export = await client.post(f"/v1/films/{code}/export", headers=auth(shooter))
    assert export.status_code == 200

    for request in (
        client.post(f"/v1/films/{code}/shots/{shot_id}/hide", headers=auth(shooter)),
        client.post(f"/v1/films/{code}/reveal", headers=auth(shooter)),
        client.patch(f"/v1/films/{code}", json={"shot_limit": 4}, headers=auth(shooter)),
        client.post(f"/v1/films/{code}/checkout", json={"tier_id": "g50"}, headers=auth(shooter)),
    ):
        assert (await request).status_code == 403


async def test_cohost_cannot_see_the_owners_money_or_hand_out_access(
    client: AsyncClient, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    _, cohost = await invite_seat(client, code, host, role="cohost")

    # Receipts and the recovery email belong to whoever paid.
    assert (await client.get(f"/v1/films/{code}/payments", headers=auth(cohost))).status_code == 403
    assert (
        await client.get(f"/v1/films/{code}/host/account", headers=auth(cohost))
    ).status_code == 403
    assert (await client.get(f"/v1/films/{code}/seats", headers=auth(cohost))).status_code == 403
    assert (
        await client.post(
            f"/v1/films/{code}/seats",
            json={"role": "photographer", "label": "Nope"},
            headers=auth(cohost),
        )
    ).status_code == 403


async def test_revoking_a_seat_takes_effect_immediately(
    client: AsyncClient, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    seat_id, cohost = await invite_seat(client, code, host, role="cohost")

    assert (await client.get(f"/v1/films/{code}/review", headers=auth(cohost))).status_code == 200

    removed = await client.delete(f"/v1/films/{code}/seats/{seat_id}", headers=auth(host))
    assert removed.status_code == 204

    # Same token, next request. Nothing waits for the year-long JWT to expire.
    assert (await client.get(f"/v1/films/{code}/review", headers=auth(cohost))).status_code == 403
    assert (await client.post(f"/v1/films/{code}/reveal", headers=auth(cohost))).status_code == 403

    listed = await client.get(f"/v1/films/{code}/seats", headers=auth(host))
    assert listed.json()["seats"] == []


async def test_a_revoked_invite_cannot_be_claimed_again(
    client: AsyncClient, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    created = await client.post(
        f"/v1/films/{code}/seats",
        json={"role": "cohost", "label": "Sam"},
        headers=auth(host),
    )
    invite = created.json()["invite_token"]
    seat_id = created.json()["seat"]["id"]
    await client.delete(f"/v1/films/{code}/seats/{seat_id}", headers=auth(host))

    claimed = await client.post(f"/v1/films/{code}/seats/claim", json={"invite_token": invite})
    assert claimed.status_code == 403


async def test_an_invite_is_scoped_to_one_film(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    other, _ = await make_film(client, closes_at=future, reveal_at=future, title="Other")
    created = await client.post(
        f"/v1/films/{code}/seats",
        json={"role": "cohost", "label": "Sam"},
        headers=auth(host),
    )

    stolen = await client.post(
        f"/v1/films/{other}/seats/claim",
        json={"invite_token": created.json()["invite_token"]},
    )
    assert stolen.status_code == 403


async def test_a_seat_token_does_not_work_on_another_film(
    client: AsyncClient, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    other, _ = await make_film(client, closes_at=future, reveal_at=future, title="Other")
    _, cohost = await invite_seat(client, code, host, role="cohost")

    response = await client.get(f"/v1/films/{other}/review", headers=auth(cohost))
    assert response.status_code == 403


async def test_guest_cannot_claim_or_manage_seats(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    guest = await join(client, code)
    assert (await client.get(f"/v1/films/{code}/seats", headers=auth(guest))).status_code == 403

    junk = await client.post(f"/v1/films/{code}/seats/claim", json={"invite_token": "x" * 40})
    assert junk.status_code == 400


async def test_revoking_an_unknown_seat_is_404(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    response = await client.delete(f"/v1/films/{code}/seats/{uuid.uuid4()}", headers=auth(host))
    assert response.status_code == 404


async def test_seats_are_capped(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    for index in range(MAX_ACTIVE_SEATS):
        created = await client.post(
            f"/v1/films/{code}/seats",
            json={"role": "photographer", "label": f"Shooter {index}"},
            headers=auth(host),
        )
        assert created.status_code == 201, created.text

    overflow = await client.post(
        f"/v1/films/{code}/seats",
        json={"role": "photographer", "label": "One too many"},
        headers=auth(host),
    )
    assert overflow.status_code == 409


async def test_an_unknown_role_is_rejected(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    response = await client.post(
        f"/v1/films/{code}/seats",
        json={"role": "owner", "label": "Nice try"},
        headers=auth(host),
    )
    assert response.status_code == 422
