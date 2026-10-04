"""The reveal boundary.

If any of these fail, the product's central promise is broken: photos stay
sealed until the film develops.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import AsyncClient

from tests.conftest import auth, join, make_film, upload_shot

pytestmark = pytest.mark.integration


async def test_gallery_exposes_no_urls_before_reveal(client: AsyncClient, future):
    code, _ = await make_film(client, closes_at=future, reveal_at=future)
    token = await join(client, code)
    await upload_shot(client, code, token)

    response = await client.get(f"/v1/films/{code}/gallery")
    body = response.json()

    assert body["is_developed"] is False
    assert body["photos"] == []
    # The count is intentionally public: guests should see the roll filling up.
    assert body["shot_count"] == 1

    # Belt and braces. Nothing resembling a link may appear anywhere in the
    # payload, including fields added later by someone unaware of this rule.
    assert "http" not in json.dumps(body)


async def test_photo_bytes_are_not_publicly_reachable(client: AsyncClient, future):
    code, _ = await make_film(client, closes_at=future, reveal_at=future)
    token = await join(client, code)

    reserved = await client.post(
        f"/v1/films/{code}/shots/reserve",
        json={"shot_id": "11111111-1111-4111-8111-111111111111"},
        headers=auth(token),
    )
    key = reserved.json()["storage_key"]

    async with httpx.AsyncClient() as raw:
        direct = await raw.get(f"http://minio:9000/filmroll-test/{key}")

    assert direct.status_code == 403


async def test_film_develops_on_schedule_without_any_worker(client: AsyncClient, past):
    """Reveal is derived, not a flag flipped by a scheduler.

    Nothing in this test runs Celery or Beat. If reveal depended on a background
    job, a dead worker would mean a wedding gallery that never opens.
    """
    closes = datetime.now(UTC) + timedelta(hours=1)
    code, _ = await make_film(client, closes_at=closes, reveal_at=past)

    body = (await client.get(f"/v1/films/{code}/gallery")).json()
    assert body["is_developed"] is True


async def test_host_can_develop_early(client: AsyncClient, future):
    code, host_token = await make_film(client, closes_at=future, reveal_at=future)
    token = await join(client, code)
    await upload_shot(client, code, token)

    assert (await client.get(f"/v1/films/{code}/gallery")).json()["is_developed"] is False

    revealed = await client.post(f"/v1/films/{code}/reveal", headers=auth(host_token))
    assert revealed.status_code == 200
    assert revealed.json()["is_developed"] is True

    body = (await client.get(f"/v1/films/{code}/gallery")).json()
    assert len(body["photos"]) == 1
    assert body["photos"][0]["url"].startswith("http")


async def test_revealing_twice_is_idempotent(client: AsyncClient, future):
    code, host_token = await make_film(client, closes_at=future, reveal_at=future)
    first = await client.post(f"/v1/films/{code}/reveal", headers=auth(host_token))
    second = await client.post(f"/v1/films/{code}/reveal", headers=auth(host_token))
    assert first.status_code == second.status_code == 200
    assert second.json()["is_developed"] is True


async def test_hidden_photos_never_appear_after_reveal(client: AsyncClient, past):
    closes = datetime.now(UTC) + timedelta(hours=1)
    code, host_token = await make_film(client, closes_at=closes, reveal_at=past)
    token = await join(client, code)
    shot_id = await upload_shot(client, code, token)
    await upload_shot(client, code, token)

    assert len((await client.get(f"/v1/films/{code}/gallery")).json()["photos"]) == 2

    hidden = await client.post(f"/v1/films/{code}/shots/{shot_id}/hide", headers=auth(host_token))
    assert hidden.status_code == 204

    photos = (await client.get(f"/v1/films/{code}/gallery")).json()["photos"]
    assert len(photos) == 1
    assert all(photo["shot_id"] != shot_id for photo in photos)


async def test_reserved_but_uncommitted_shots_stay_out_of_the_gallery(client: AsyncClient, past):
    """A reserved slot has no bytes yet and would render as a broken image."""
    closes = datetime.now(UTC) + timedelta(hours=1)
    code, _ = await make_film(client, closes_at=closes, reveal_at=past)
    token = await join(client, code)

    await client.post(
        f"/v1/films/{code}/shots/reserve",
        json={"shot_id": "22222222-2222-4222-8222-222222222222"},
        headers=auth(token),
    )

    body = (await client.get(f"/v1/films/{code}/gallery")).json()
    assert body["photos"] == []


async def _create_instant(client: AsyncClient, *, closes_at: datetime) -> tuple[str, str]:
    response = await client.post(
        "/v1/films",
        json={
            "title": "Live Film",
            "event_type": "party",
            "closes_at": closes_at.isoformat(),
            "instant_reveal": True,
            "shot_limit": 8,
            "guest_cap": 5,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["film"]["instant_reveal"] is True
    assert body["film"]["is_developed"] is True
    return body["film"]["code"], body["host_token"]


async def test_an_instant_film_is_born_developed(client: AsyncClient, future: datetime) -> None:
    """Live mode reuses the existing reveal predicate. No second way to be visible."""
    code, _ = await _create_instant(client, closes_at=future)
    film = (await client.get(f"/v1/films/{code}")).json()
    assert film["instant_reveal"] is True
    assert film["is_developed"] is True

    gallery = (await client.get(f"/v1/films/{code}/gallery")).json()
    assert gallery["is_developed"] is True
    assert gallery["photos"] == []


async def test_shots_on_an_instant_film_appear_in_the_gallery_immediately(
    client: AsyncClient, future: datetime
) -> None:
    code, _ = await _create_instant(client, closes_at=future)
    token = await join(client, code)
    shot_id = await upload_shot(client, code, token)

    gallery = (await client.get(f"/v1/films/{code}/gallery")).json()
    assert [photo["shot_id"] for photo in gallery["photos"]] == [shot_id]
    assert gallery["photos"][0]["url"].startswith("http")


async def test_hiding_still_works_on_a_live_film(client: AsyncClient, future: datetime) -> None:
    """Live is not a way around moderation. A host can still kill a shot."""
    code, host = await _create_instant(client, closes_at=future)
    token = await join(client, code)
    shot_id = await upload_shot(client, code, token)

    hidden = await client.post(f"/v1/films/{code}/shots/{shot_id}/hide", headers=auth(host))
    assert hidden.status_code == 204
    assert (await client.get(f"/v1/films/{code}/gallery")).json()["photos"] == []


async def test_a_live_film_cannot_grow_a_reveal_time(client: AsyncClient, future: datetime) -> None:
    """Once guests have seen a photo it cannot be un-seen. Instant is creation-only."""
    code, host = await _create_instant(client, closes_at=future)

    locked = await client.patch(
        f"/v1/films/{code}",
        json={"reveal_at": future.isoformat()},
        headers=auth(host),
    )
    assert locked.status_code == 409
    assert (await client.get(f"/v1/films/{code}")).json()["is_developed"] is True


async def test_a_scheduled_film_still_needs_a_reveal_time(
    client: AsyncClient, future: datetime
) -> None:
    response = await client.post(
        "/v1/films",
        json={
            "title": "Needs a time",
            "event_type": "wedding",
            "closes_at": future.isoformat(),
            "shot_limit": 8,
            "guest_cap": 5,
        },
    )
    assert response.status_code == 422


async def test_instant_reveal_is_off_by_default(client: AsyncClient, future: datetime) -> None:
    code, _ = await make_film(client, closes_at=future, reveal_at=future)
    assert (await client.get(f"/v1/films/{code}")).json()["instant_reveal"] is False
