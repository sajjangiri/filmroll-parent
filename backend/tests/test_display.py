"""The screen-sized photo the gallery offers alongside the original.

A venue slideshow reads the public gallery, so this is what keeps a projector
from downloading full-resolution originals on every slide.
"""

from __future__ import annotations

import io
import uuid
from datetime import datetime

import httpx
import pytest
from httpx import AsyncClient
from PIL import Image

from app.worker.tasks import generate_derivatives
from tests.conftest import auth, join, make_film

pytestmark = pytest.mark.integration


def _jpeg(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (200, 80, 40)).save(buffer, format="JPEG")
    return buffer.getvalue()


async def test_display_url_appears_once_the_derivative_exists(
    client: AsyncClient, future: datetime, past: datetime
) -> None:
    code, _ = await make_film(client, closes_at=future, reveal_at=past)
    token = await join(client, code)
    shot_id = str(uuid.uuid4())
    reserved = await client.post(
        f"/v1/films/{code}/shots/reserve", json={"shot_id": shot_id}, headers=auth(token)
    )
    async with httpx.AsyncClient() as raw:
        put = await raw.put(
            reserved.json()["upload_url"],
            content=_jpeg(1500, 2000),
            headers={"Content-Type": "image/jpeg"},
        )
        assert put.status_code == 200, put.text
    committed = await client.post(f"/v1/films/{code}/shots/{shot_id}/commit", headers=auth(token))
    assert committed.status_code == 200, committed.text

    [before] = (await client.get(f"/v1/films/{code}/gallery")).json()["photos"]
    assert before["display_url"] is None

    assert generate_derivatives.run(shot_id) == "ok"

    [after] = (await client.get(f"/v1/films/{code}/gallery")).json()["photos"]
    assert after["display_url"]
    async with httpx.AsyncClient() as raw:
        body = (await raw.get(after["display_url"])).content
    with Image.open(io.BytesIO(body)) as display:
        assert display.format == "WEBP"
        assert max(display.size) <= 1280
