"""Guest video clips and the video pack that unlocks them.

Clips are a separate allowance from the photo roll, gated on a paid add-on,
and never shown until the worker has transcoded them. The transcode tests need
ffmpeg, which only the media image has; run them with
``docker compose run --rm worker-media pytest tests/test_clips.py``.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.models import Film
from app.db.session import get_sessionmaker
from app.services.catalog import CLIP_MAX_SECONDS, CLIPS_PER_GUEST
from tests.conftest import auth, join, make_film, upload_shot

pytestmark = pytest.mark.integration

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs the media image")


async def _buy_pack(client: AsyncClient, code: str, host: str) -> None:
    paid = await client.post(
        f"/v1/films/{code}/checkout", json={"addon_id": "video_pack"}, headers=auth(host)
    )
    assert paid.status_code == 200, paid.text


async def _reserve_clip(
    client: AsyncClient, code: str, token: str, content_type: str = "video/mp4"
) -> httpx.Response:
    return await client.post(
        f"/v1/films/{code}/shots/reserve",
        json={"shot_id": str(uuid.uuid4()), "kind": "clip", "content_type": content_type},
        headers=auth(token),
    )


async def _upload_clip(client: AsyncClient, code: str, token: str, body: bytes) -> str:
    reserved = await _reserve_clip(client, code, token)
    assert reserved.status_code == 200, reserved.text
    data = reserved.json()
    async with httpx.AsyncClient() as raw:
        put = await raw.put(
            data["upload_url"], content=body, headers={"Content-Type": data["content_type"]}
        )
        assert put.status_code == 200, put.text
    committed = await client.post(
        f"/v1/films/{code}/shots/{data['shot_id']}/commit", headers=auth(token)
    )
    assert committed.status_code == 200, committed.text
    return str(data["shot_id"])


async def test_video_pack_is_in_the_catalog(client: AsyncClient) -> None:
    body = (await client.get("/v1/billing/catalog")).json()
    assert any(addon["id"] == "video_pack" for addon in body["addons"])


async def test_clips_need_the_video_pack(client: AsyncClient, future: datetime) -> None:
    code, _ = await make_film(client, closes_at=future, reveal_at=future)
    token = await join(client, code)

    film = (await client.get(f"/v1/films/{code}")).json()
    assert film["video_pack"] is False
    assert film["clips_per_guest"] == 0

    response = await _reserve_clip(client, code, token)
    assert response.status_code == 402, response.text


async def test_the_pack_is_bought_once(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    await _buy_pack(client, code, host)
    again = await client.post(
        f"/v1/films/{code}/checkout", json={"addon_id": "video_pack"}, headers=auth(host)
    )
    assert again.status_code == 409, again.text


async def test_clip_allowance_is_separate_from_the_roll(
    client: AsyncClient, future: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future, shot_limit=1)
    await _buy_pack(client, code, host)

    film = (await client.get(f"/v1/films/{code}")).json()
    assert film["video_pack"] is True
    assert film["clips_per_guest"] == CLIPS_PER_GUEST
    assert film["clip_max_seconds"] == CLIP_MAX_SECONDS

    joined = await client.post(f"/v1/films/{code}/join", json={"display_name": "Ana"})
    assert joined.json()["clips_remaining"] == CLIPS_PER_GUEST
    token = joined.json()["guest_token"]

    # Spending the only photo leaves every clip.
    await upload_shot(client, code, token)
    for used in range(1, CLIPS_PER_GUEST + 1):
        reserved = await _reserve_clip(client, code, token)
        assert reserved.status_code == 200, reserved.text
        assert reserved.json()["clips_remaining"] == CLIPS_PER_GUEST - used
        assert reserved.json()["shots_remaining"] == 0

    over = await _reserve_clip(client, code, token)
    assert over.status_code == 409, over.text
    assert "clip" in over.json()["detail"]


async def test_clips_do_not_spend_photos(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future, shot_limit=2)
    await _buy_pack(client, code, host)
    token = await join(client, code)

    reserved = await _reserve_clip(client, code, token)
    assert reserved.json()["shots_remaining"] == 2
    await upload_shot(client, code, token)
    await upload_shot(client, code, token)


async def test_a_clip_must_be_video(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future)
    await _buy_pack(client, code, host)
    token = await join(client, code)

    rejected = await _reserve_clip(client, code, token, content_type="image/jpeg")
    assert rejected.status_code == 415, rejected.text

    # Browsers append codec parameters; the base type is what counts.
    webm = await _reserve_clip(client, code, token, content_type="video/webm;codecs=vp9,opus")
    assert webm.status_code == 200, webm.text
    assert webm.json()["content_type"] == "video/webm"
    assert webm.json()["storage_key"].endswith(".webm")


async def test_an_untranscoded_clip_is_never_shown(
    client: AsyncClient, future: datetime, past: datetime
) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=past)
    await _buy_pack(client, code, host)
    token = await join(client, code)
    await _upload_clip(client, code, token, b"\x00\x00\x00\x18ftypmp42")

    gallery = (await client.get(f"/v1/films/{code}/gallery")).json()
    assert gallery["photos"] == []
    review = (await client.get(f"/v1/films/{code}/review", headers=auth(host))).json()
    assert review["photos"] == []


# ----------------------------------------------------------------- transcode


def _make_source(path: Path, seconds: int) -> bytes:
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc=size=1920x1080:rate=30:duration={seconds}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
            "-metadata", "location=+48.8584+002.2945/",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest",
            str(path),
        ],
        check=True,
    )  # fmt: skip
    return path.read_bytes()


def _probe(data: bytes, tmp_path: Path) -> str:
    target = tmp_path / "probe.mp4"
    target.write_bytes(data)
    return subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", str(target)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@needs_ffmpeg
async def test_transcode_trims_strips_and_serves(
    client: AsyncClient, future: datetime, past: datetime, tmp_path: Path
) -> None:
    from app.services import storage
    from app.worker.tasks import build_export_archive_for_film, transcode_clip

    code, host = await make_film(client, closes_at=future, reveal_at=past)
    await _buy_pack(client, code, host)
    token = await join(client, code, "Ana")
    source = _make_source(tmp_path / "long.mp4", CLIP_MAX_SECONDS + 5)
    assert "+48.8584" in _probe(source, tmp_path)
    shot_id = await _upload_clip(client, code, token, source)

    assert transcode_clip.run(shot_id) == "ok"
    assert transcode_clip.run(shot_id) == "already-done"

    gallery = (await client.get(f"/v1/films/{code}/gallery")).json()
    [clip] = gallery["photos"]
    assert clip["kind"] == "clip"
    assert clip["poster_url"]
    assert clip["duration_ms"] <= CLIP_MAX_SECONDS * 1000 + 100

    async with httpx.AsyncClient() as raw:
        video = (await raw.get(clip["url"])).content
        poster = await raw.get(clip["poster_url"])
    assert poster.status_code == 200

    info = _probe(video, tmp_path)
    assert "codec_name=h264" in info
    assert "codec_name=aac" in info
    assert "+48.8584" not in info
    assert "height=720" in info

    async with get_sessionmaker()() as session:
        film = await session.scalar(select(Film).where(Film.code == code))
        assert film is not None
        film_id = str(film.id)
    key = build_export_archive_for_film(film_id)
    archive = zipfile.ZipFile(io.BytesIO(storage.download_bytes(key)))
    [name] = archive.namelist()
    assert name.endswith(".mp4")
