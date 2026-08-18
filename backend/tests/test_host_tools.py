"""Host tools: review before reveal, print cards, ZIP originals, live settings."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.models import Film
from app.db.session import get_sessionmaker
from app.worker.tasks import build_export_archive_for_film
from tests.conftest import auth, join, make_film, upload_shot

pytestmark = pytest.mark.integration


async def _film_id(code: str) -> str:
    async with get_sessionmaker()() as session:
        film = await session.scalar(select(Film).where(Film.code == code.upper()))
        assert film is not None
        return str(film.id)


async def test_host_can_see_photos_before_reveal(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    token = await join(client, code, "Ada")
    shot_id = await upload_shot(client, code, token)

    gallery = await client.get(f"/v1/films/{code}/gallery")
    assert gallery.json()["photos"] == []

    review = await client.get(f"/v1/films/{code}/review", headers=auth(host))
    assert review.status_code == 200, review.text
    body = review.json()
    assert body["shot_count"] == 1
    assert body["photos"][0]["shot_id"] == shot_id
    assert body["photos"][0]["guest_name"] == "Ada"
    assert body["photos"][0]["hidden"] is False
    assert body["photos"][0]["url"].startswith("http")


async def test_guest_cannot_open_the_host_inbox(client: AsyncClient, future: datetime) -> None:
    code, _ = await make_film(client, closes_at=future, reveal_at=future)
    guest = await join(client, code)
    await upload_shot(client, code, guest)

    assert (await client.get(f"/v1/films/{code}/review", headers=auth(guest))).status_code == 403
    assert (await client.get(f"/v1/films/{code}/review")).status_code == 401


async def test_hiding_before_reveal_keeps_the_photo_out_of_the_gallery(
    client: AsyncClient, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    token = await join(client, code)
    shot_id = await upload_shot(client, code, token)

    hidden = await client.post(f"/v1/films/{code}/shots/{shot_id}/hide", headers=auth(host))
    assert hidden.status_code == 204

    await client.post(f"/v1/films/{code}/reveal", headers=auth(host))
    gallery = await client.get(f"/v1/films/{code}/gallery")
    assert gallery.json()["photos"] == []

    review = await client.get(f"/v1/films/{code}/review", headers=auth(host))
    assert review.json()["photos"][0]["hidden"] is True
    assert review.json()["hidden_count"] == 1


async def test_unhide_puts_a_photo_back(client: AsyncClient, past: datetime) -> None:
    closes = datetime.now(UTC) + timedelta(hours=1)
    code, host = await make_film(client, closes_at=closes, reveal_at=past)
    token = await join(client, code)
    shot_id = await upload_shot(client, code, token)

    await client.post(f"/v1/films/{code}/shots/{shot_id}/hide", headers=auth(host))
    await client.post(f"/v1/films/{code}/shots/{shot_id}/unhide", headers=auth(host))

    photos = (await client.get(f"/v1/films/{code}/gallery")).json()["photos"]
    assert len(photos) == 1
    assert photos[0]["shot_id"] == shot_id


async def test_guest_can_retract_only_their_own_photo(client: AsyncClient, past: datetime) -> None:
    closes = datetime.now(UTC) + timedelta(hours=1)
    code, _ = await make_film(client, closes_at=closes, reveal_at=past)
    ada = await join(client, code, "Ada")
    jon = await join(client, code, "Jon")
    ada_shot = await upload_shot(client, code, ada)
    jon_shot = await upload_shot(client, code, jon)

    stolen = await client.delete(f"/v1/films/{code}/shots/{jon_shot}", headers=auth(ada))
    assert stolen.status_code == 404

    own = await client.delete(f"/v1/films/{code}/shots/{ada_shot}", headers=auth(ada))
    assert own.status_code == 204

    photos = (await client.get(f"/v1/films/{code}/gallery")).json()["photos"]
    assert [p["shot_id"] for p in photos] == [jon_shot]


async def test_host_cannot_drop_the_guest_cap_below_headcount(
    client: AsyncClient, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future, guest_cap=5)
    await join(client, code, "Ada")
    await join(client, code, "Jon")

    too_low = await client.patch(f"/v1/films/{code}", json={"guest_cap": 1}, headers=auth(host))
    assert too_low.status_code == 409

    raised = await client.patch(f"/v1/films/{code}", json={"guest_cap": 40}, headers=auth(host))
    assert raised.status_code == 200
    assert raised.json()["guest_cap"] == 40
    assert raised.json()["shot_count"] == 0


async def test_cards_pdf_is_ours_and_names_the_film(client: AsyncClient, future: datetime) -> None:
    code, _ = await make_film(client, closes_at=future, reveal_at=future, title="Maya and Jon")
    response = await client.get(f"/v1/films/{code}/cards.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    body = response.content
    assert body.startswith(b"%PDF")
    assert b"Maya and Jon" in body
    assert code.encode() in body
    assert b"qrserver" not in body


@pytest.mark.worker
async def test_export_zip_contains_originals_and_omits_hidden(
    client: AsyncClient, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    token = await join(client, code, "Ada")
    await upload_shot(client, code, token)
    drop = await upload_shot(client, code, token)
    await client.post(f"/v1/films/{code}/shots/{drop}/hide", headers=auth(host))

    film_id = await _film_id(code)
    key = build_export_archive_for_film(film_id)
    assert key.endswith("originals.zip")

    status = await client.get(f"/v1/films/{code}/export", headers=auth(host))
    assert status.status_code == 200, status.text
    assert status.json()["status"] == "ready"
    assert status.json()["shot_count"] == 1
    url = status.json()["download_url"]
    assert url and url.startswith("http")

    async with httpx.AsyncClient() as raw:
        downloaded = await raw.get(url)
    assert downloaded.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(downloaded.content))
    names = archive.namelist()
    assert len(names) == 1
    assert all(drop[:8] not in name for name in names)

    guest = await join(client, code, "Eve")
    assert (await client.get(f"/v1/films/{code}/export", headers=auth(guest))).status_code == 403
