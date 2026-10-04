"""Private vs shared gallery.

The product default is a shared album: after develop, everyone at the event
sees everyone else's shots. Private is the other setting — each guest only
sees their own roll. The host inbox and ZIP still hold the whole film, because
that is the couple's copy, not the party feed.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from httpx import AsyncClient

from tests.conftest import auth, join, make_film, upload_shot

pytestmark = pytest.mark.integration


async def test_gallery_is_shared_by_default(
    client: AsyncClient, past: datetime, future: datetime
) -> None:
    code, _ = await make_film(client, closes_at=future, reveal_at=past)
    assert (await client.get(f"/v1/films/{code}")).json()["shared_gallery"] is True

    alice = await join(client, code, "Alice")
    bob = await join(client, code, "Bob")
    shot = await upload_shot(client, code, alice)

    photos = (await client.get(f"/v1/films/{code}/gallery")).json()["photos"]
    assert [p["shot_id"] for p in photos] == [shot]
    # Bob sees Alice's shot without being Alice. That is the shared album.
    as_bob = (await client.get(f"/v1/films/{code}/gallery", headers=auth(bob))).json()["photos"]
    assert [p["shot_id"] for p in as_bob] == [shot]


async def test_a_private_gallery_hides_other_peoples_shots(
    client: AsyncClient, past: datetime, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=past)
    switched = await client.patch(
        f"/v1/films/{code}", json={"shared_gallery": False}, headers=auth(host)
    )
    assert switched.status_code == 200
    assert switched.json()["shared_gallery"] is False

    alice = await join(client, code, "Alice")
    bob = await join(client, code, "Bob")
    alices = await upload_shot(client, code, alice)
    bobs = await upload_shot(client, code, bob)

    as_alice = (await client.get(f"/v1/films/{code}/gallery", headers=auth(alice))).json()
    assert [p["shot_id"] for p in as_alice["photos"]] == [alices]

    as_bob = (await client.get(f"/v1/films/{code}/gallery", headers=auth(bob))).json()
    assert [p["shot_id"] for p in as_bob["photos"]] == [bobs]


async def test_an_anonymous_viewer_gets_no_urls_from_a_private_film(
    client: AsyncClient, past: datetime, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=past)
    await client.patch(f"/v1/films/{code}", json={"shared_gallery": False}, headers=auth(host))
    guest = await join(client, code, "Alice")
    await upload_shot(client, code, guest)

    public = await client.get(f"/v1/films/{code}/gallery")
    body = public.json()
    assert body["is_developed"] is True
    assert body["photos"] == []
    assert "http" not in public.text
    # The count still says the roll is filling. The URLs do not.
    assert body["shot_count"] == 1


async def test_a_host_token_does_not_unlock_the_private_gallery(
    client: AsyncClient, past: datetime, future: datetime
) -> None:
    """The inbox is how the host sees every shot. The public gallery is not."""
    code, host = await make_film(client, closes_at=future, reveal_at=past)
    await client.patch(f"/v1/films/{code}", json={"shared_gallery": False}, headers=auth(host))
    guest = await join(client, code, "Alice")
    shot = await upload_shot(client, code, guest)

    leaked = await client.get(f"/v1/films/{code}/gallery", headers=auth(host))
    assert leaked.json()["photos"] == []

    review = await client.get(f"/v1/films/{code}/review", headers=auth(host))
    assert [p["shot_id"] for p in review.json()["photos"]] == [shot]


async def test_export_still_includes_every_shot_on_a_private_film(
    client: AsyncClient, past: datetime, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=past)
    await client.patch(f"/v1/films/{code}", json={"shared_gallery": False}, headers=auth(host))
    alice = await join(client, code, "Alice")
    bob = await join(client, code, "Bob")
    await upload_shot(client, code, alice)
    await upload_shot(client, code, bob)

    started = await client.post(f"/v1/films/{code}/export", headers=auth(host))
    assert started.status_code == 200
    assert started.json()["shot_count"] == 2


async def test_sharing_later_opens_the_album(
    client: AsyncClient, past: datetime, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=past)
    await client.patch(f"/v1/films/{code}", json={"shared_gallery": False}, headers=auth(host))
    alice = await join(client, code, "Alice")
    bob = await join(client, code, "Bob")
    shot = await upload_shot(client, code, alice)

    assert (await client.get(f"/v1/films/{code}/gallery", headers=auth(bob))).json()["photos"] == []

    opened = await client.patch(
        f"/v1/films/{code}", json={"shared_gallery": True}, headers=auth(host)
    )
    assert opened.json()["shared_gallery"] is True
    as_bob = (await client.get(f"/v1/films/{code}/gallery", headers=auth(bob))).json()["photos"]
    assert [p["shot_id"] for p in as_bob] == [shot]


async def test_a_guest_cannot_flip_visibility(
    client: AsyncClient, past: datetime, future: datetime
) -> None:
    code, _ = await make_film(client, closes_at=future, reveal_at=past)
    guest = await join(client, code)
    response = await client.patch(
        f"/v1/films/{code}", json={"shared_gallery": False}, headers=auth(guest)
    )
    assert response.status_code == 403


async def test_creating_a_private_film(client: AsyncClient, future: datetime) -> None:
    response = await client.post(
        "/v1/films",
        json={
            "title": "Private party",
            "event_type": "party",
            "closes_at": future.isoformat(),
            "reveal_at": future.isoformat(),
            "shot_limit": 8,
            "guest_cap": 5,
            "shared_gallery": False,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["film"]["shared_gallery"] is False
