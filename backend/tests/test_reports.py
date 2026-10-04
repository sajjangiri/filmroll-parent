"""Guests reporting a photo.

A report is a signal to the host, never an action. The assertions that matter
are that a report changes nothing about who can see the photo, that one guest
cannot manufacture a crowd, and that the host learns the count without learning
who raised it — a report must not start an argument between two people at the
same wedding.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from httpx import AsyncClient

from tests.conftest import auth, invite_seat, join, make_film, upload_shot

pytestmark = pytest.mark.integration


async def _review(client: AsyncClient, code: str, token: str) -> dict:
    response = await client.get(f"/v1/films/{code}/review", headers=auth(token))
    assert response.status_code == 200, response.text
    return response.json()


async def test_a_guest_can_report_a_photo(
    client: AsyncClient, past: datetime, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=past)
    shooter = await join(client, code, "Shooter")
    watcher = await join(client, code, "Watcher")
    shot_id = await upload_shot(client, code, shooter)

    response = await client.post(
        f"/v1/films/{code}/shots/{shot_id}/report",
        json={"reason": "inappropriate"},
        headers=auth(watcher),
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"shot_id": shot_id, "report_count": 1}


async def test_reporting_does_not_hide_the_photo(
    client: AsyncClient, past: datetime, future: datetime
) -> None:
    """Moderation stays a human decision. A brigade must not be able to censor."""
    code, host = await make_film(client, closes_at=future, reveal_at=past)
    shooter = await join(client, code, "Shooter")
    shot_id = await upload_shot(client, code, shooter)

    for index in range(5):
        watcher = await join(client, code, f"Watcher {index}")
        await client.post(
            f"/v1/films/{code}/shots/{shot_id}/report",
            json={"reason": "inappropriate"},
            headers=auth(watcher),
        )

    gallery = await client.get(f"/v1/films/{code}/gallery")
    assert [photo["shot_id"] for photo in gallery.json()["photos"]] == [shot_id]

    review = await _review(client, code, host)
    assert review["photos"][0]["hidden"] is False
    assert review["photos"][0]["report_count"] == 5


async def test_one_guest_cannot_manufacture_a_crowd(
    client: AsyncClient, past: datetime, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=past)
    shooter = await join(client, code, "Shooter")
    watcher = await join(client, code, "Watcher")
    shot_id = await upload_shot(client, code, shooter)

    for reason in ("inappropriate", "private", "other"):
        response = await client.post(
            f"/v1/films/{code}/shots/{shot_id}/report",
            json={"reason": reason},
            headers=auth(watcher),
        )
        assert response.status_code == 200
        assert response.json()["report_count"] == 1

    assert (await _review(client, code, host))["photos"][0]["report_count"] == 1


async def test_the_host_sees_the_count_but_not_the_reporter(
    client: AsyncClient, past: datetime, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=past)
    shooter = await join(client, code, "Shooter")
    watcher = await join(client, code, "Delilah")
    shot_id = await upload_shot(client, code, shooter)
    await client.post(
        f"/v1/films/{code}/shots/{shot_id}/report",
        json={"reason": "private"},
        headers=auth(watcher),
    )

    body = (await client.get(f"/v1/films/{code}/review", headers=auth(host))).text
    assert "Delilah" not in body
    assert "private" not in body


async def test_reported_count_tracks_what_still_needs_the_host(
    client: AsyncClient, past: datetime, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=past)
    shooter = await join(client, code, "Shooter")
    watcher = await join(client, code, "Watcher")
    first = await upload_shot(client, code, shooter)
    second = await upload_shot(client, code, shooter)

    for shot_id in (first, second):
        await client.post(
            f"/v1/films/{code}/shots/{shot_id}/report",
            json={"reason": "other"},
            headers=auth(watcher),
        )
    assert (await _review(client, code, host))["reported_count"] == 2

    # Acting on one takes it off the list; the report itself is still recorded.
    await client.post(f"/v1/films/{code}/shots/{first}/hide", headers=auth(host))
    review = await _review(client, code, host)
    assert review["reported_count"] == 1
    hidden = next(p for p in review["photos"] if p["shot_id"] == first)
    assert hidden["report_count"] == 1


async def test_a_film_with_no_reports_says_so(
    client: AsyncClient, past: datetime, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=past)
    shooter = await join(client, code, "Shooter")
    await upload_shot(client, code, shooter)

    review = await _review(client, code, host)
    assert review["reported_count"] == 0
    assert review["photos"][0]["report_count"] == 0


async def test_reporting_requires_a_guest_token(
    client: AsyncClient, past: datetime, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=past)
    shooter = await join(client, code, "Shooter")
    shot_id = await upload_shot(client, code, shooter)
    _, cohost = await invite_seat(client, code, host, role="cohost")

    # Anyone can open the gallery link; only people who joined can report.
    assert (
        await client.post(f"/v1/films/{code}/shots/{shot_id}/report", json={"reason": "other"})
    ).status_code == 401
    assert (
        await client.post(
            f"/v1/films/{code}/shots/{shot_id}/report",
            json={"reason": "other"},
            headers=auth(host),
        )
    ).status_code == 403
    assert (
        await client.post(
            f"/v1/films/{code}/shots/{shot_id}/report",
            json={"reason": "other"},
            headers=auth(cohost),
        )
    ).status_code == 403


async def test_a_guest_cannot_report_into_another_film(
    client: AsyncClient, past: datetime, future: datetime
) -> None:
    code, _ = await make_film(client, closes_at=future, reveal_at=past)
    other, _ = await make_film(client, closes_at=future, reveal_at=past, title="Other")
    shooter = await join(client, code, "Shooter")
    shot_id = await upload_shot(client, code, shooter)
    outsider = await join(client, other, "Outsider")

    response = await client.post(
        f"/v1/films/{other}/shots/{shot_id}/report",
        json={"reason": "other"},
        headers=auth(outsider),
    )
    assert response.status_code == 404


async def test_reporting_an_unknown_shot_is_404(
    client: AsyncClient, past: datetime, future: datetime
) -> None:
    code, _ = await make_film(client, closes_at=future, reveal_at=past)
    guest = await join(client, code)
    response = await client.post(
        f"/v1/films/{code}/shots/{uuid.uuid4()}/report",
        json={"reason": "other"},
        headers=auth(guest),
    )
    assert response.status_code == 404


async def test_an_unknown_reason_is_rejected(
    client: AsyncClient, past: datetime, future: datetime
) -> None:
    code, _ = await make_film(client, closes_at=future, reveal_at=past)
    shooter = await join(client, code, "Shooter")
    shot_id = await upload_shot(client, code, shooter)
    guest = await join(client, code, "Watcher")

    response = await client.post(
        f"/v1/films/{code}/shots/{shot_id}/report",
        json={"reason": "i just dont like it"},
        headers=auth(guest),
    )
    assert response.status_code == 422


async def test_a_guest_can_report_their_own_shot(
    client: AsyncClient, past: datetime, future: datetime
) -> None:
    """Regret is a real reason. Retracting is better, but this must not error."""
    code, host = await make_film(client, closes_at=future, reveal_at=past)
    shooter = await join(client, code, "Shooter")
    shot_id = await upload_shot(client, code, shooter)

    response = await client.post(
        f"/v1/films/{code}/shots/{shot_id}/report",
        json={"reason": "private"},
        headers=auth(shooter),
    )
    assert response.status_code == 200
    assert (await _review(client, code, host))["photos"][0]["report_count"] == 1


async def test_reports_vanish_with_the_shot(
    client: AsyncClient, past: datetime, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=past)
    shooter = await join(client, code, "Shooter")
    watcher = await join(client, code, "Watcher")
    shot_id = await upload_shot(client, code, shooter)
    await client.post(
        f"/v1/films/{code}/shots/{shot_id}/report",
        json={"reason": "other"},
        headers=auth(watcher),
    )

    retracted = await client.delete(f"/v1/films/{code}/shots/{shot_id}", headers=auth(shooter))
    assert retracted.status_code == 204

    review = await _review(client, code, host)
    assert review["reported_count"] == 0
