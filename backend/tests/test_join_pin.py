"""The optional join PIN.

The threat is mundane: a QR card sits on a table all night, and anyone who
photographs it can otherwise walk into a private event. So the interesting
assertions here are about who is turned away, that the digits never appear in a
response, and that guests already holding a camera are not locked out when the
host adds a PIN mid-event.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.services import pins
from tests.conftest import auth, invite_seat, join, make_film, upload_shot

pytestmark = pytest.mark.integration


async def _set_pin(client: AsyncClient, code: str, token: str, pin: str) -> None:
    response = await client.put(f"/v1/films/{code}/pin", json={"pin": pin}, headers=auth(token))
    assert response.status_code == 200, response.text
    assert response.json()["requires_pin"] is True


async def test_a_film_has_no_pin_by_default(client: AsyncClient, future: datetime) -> None:
    code, _ = await make_film(client, closes_at=future, reveal_at=future)
    assert (await client.get(f"/v1/films/{code}")).json()["requires_pin"] is False
    # Joining without one still works, which is the common case.
    assert await join(client, code)


async def test_the_right_pin_lets_a_guest_in(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    await _set_pin(client, code, host, "4821")

    response = await client.post(
        f"/v1/films/{code}/join", json={"display_name": "Ada", "join_pin": "4821"}
    )
    assert response.status_code == 201, response.text
    assert response.json()["display_name"] == "Ada"


async def test_a_wrong_or_missing_pin_is_refused(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    await _set_pin(client, code, host, "4821")

    for body in (
        {"display_name": "Nope"},
        {"display_name": "Nope", "join_pin": ""},
        {"display_name": "Nope", "join_pin": "0000"},
        {"display_name": "Nope", "join_pin": "not-digits"},
    ):
        response = await client.post(f"/v1/films/{code}/join", json=body)
        assert response.status_code == 403, response.text

    # A refused join must not consume a seat in the film.
    assert (await client.get(f"/v1/films/{code}")).json()["guest_count"] == 0


async def test_the_pin_is_never_returned(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    await _set_pin(client, code, host, "4821")

    public = (await client.get(f"/v1/films/{code}")).text
    assert "4821" not in public
    assert "join_pin" not in public
    # Not even to the host, who set it and cannot read it back.
    assert "4821" not in (await client.get(f"/v1/films/{code}/review", headers=auth(host))).text


async def test_a_pin_added_mid_event_does_not_evict_guests(
    client: AsyncClient, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    guest = await join(client, code, "Early")

    await _set_pin(client, code, host, "4821")

    # The guest token is what proves they joined; the PIN gated the door, not
    # the camera they are already holding.
    assert await upload_shot(client, code, guest)


async def test_clearing_the_pin_reopens_the_film(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    await _set_pin(client, code, host, "4821")

    cleared = await client.delete(f"/v1/films/{code}/pin", headers=auth(host))
    assert cleared.status_code == 200
    assert cleared.json()["requires_pin"] is False

    assert (
        await client.post(f"/v1/films/{code}/join", json={"display_name": "Ada"})
    ).status_code == 201


async def test_the_pin_can_be_changed(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    await _set_pin(client, code, host, "4821")
    await _set_pin(client, code, host, "999111")

    assert (
        await client.post(
            f"/v1/films/{code}/join", json={"display_name": "Old", "join_pin": "4821"}
        )
    ).status_code == 403
    assert (
        await client.post(
            f"/v1/films/{code}/join", json={"display_name": "New", "join_pin": "999111"}
        )
    ).status_code == 201


async def test_spacing_a_pin_out_still_works(client: AsyncClient, future: datetime) -> None:
    """Hosts read these aloud and guests type what they hear."""
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    await _set_pin(client, code, host, "482134")

    response = await client.post(
        f"/v1/films/{code}/join", json={"display_name": "Ada", "join_pin": "482 134"}
    )
    assert response.status_code == 201, response.text


async def test_a_malformed_pin_is_rejected_at_the_door(
    client: AsyncClient, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    for bad in ("123", "abcd", "1234567890123"):
        response = await client.put(f"/v1/films/{code}/pin", json={"pin": bad}, headers=auth(host))
        assert response.status_code == 422, f"{bad} was accepted"


async def test_a_cohost_can_manage_the_pin_but_a_guest_cannot(
    client: AsyncClient, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    guest = await join(client, code)
    _, cohost = await invite_seat(client, code, host, role="cohost")
    _, shooter = await invite_seat(client, code, host, role="photographer")

    # Whoever is working the door needs this, and that is often not the couple.
    assert (
        await client.put(f"/v1/films/{code}/pin", json={"pin": "4821"}, headers=auth(cohost))
    ).status_code == 200
    assert (
        await client.put(f"/v1/films/{code}/pin", json={"pin": "1111"}, headers=auth(shooter))
    ).status_code == 403
    assert (
        await client.put(f"/v1/films/{code}/pin", json={"pin": "1111"}, headers=auth(guest))
    ).status_code == 403
    assert (await client.delete(f"/v1/films/{code}/pin", headers=auth(guest))).status_code == 403


async def test_guessing_burns_the_join_allowance(
    client: AsyncClient, future: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A four-digit secret is only meaningful because guesses are rationed."""
    monkeypatch.setattr(get_settings(), "rate_limit_join_per_hour", 5)
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    await _set_pin(client, code, host, "4821")

    statuses = [
        (
            await client.post(
                f"/v1/films/{code}/join",
                json={"display_name": "Guess", "join_pin": f"000{n}"},
            )
        ).status_code
        for n in range(7)
    ]
    assert statuses[0] == 403
    # The limiter cuts in before the attacker exhausts the keyspace, and it does
    # so whether or not the guess happened to be correct.
    assert 429 in statuses


async def test_pin_hashing_is_keyed_and_stable() -> None:
    assert pins.hash_pin("4821") == pins.hash_pin("4821")
    assert pins.hash_pin("4821") != pins.hash_pin("4822")
    # The digits must not be recoverable by looking at the stored value.
    assert "4821" not in pins.hash_pin("4821")
    assert pins.matches(None, None) is True
    assert pins.matches(pins.hash_pin("4821"), "4821") is True
    assert pins.matches(pins.hash_pin("4821"), None) is False
