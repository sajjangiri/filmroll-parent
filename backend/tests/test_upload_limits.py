"""What happens when a client uploads something it should not.

A presigned PUT is a capability, not a contract. It names a key and a content
type, but nothing stops the holder from writing a gigabyte of video to it. These
tests cover the checks that run once the bytes exist.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import httpx
import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from tests.conftest import TINY_JPEG, auth, join, make_film

pytestmark = pytest.mark.integration


async def _reserve(client: AsyncClient, code: str, token: str) -> tuple[str, str]:
    shot_id = str(uuid.uuid4())
    reserved = await client.post(
        f"/v1/films/{code}/shots/reserve",
        json={"shot_id": shot_id},
        headers=auth(token),
    )
    assert reserved.status_code == 200, reserved.text
    return shot_id, reserved.json()["upload_url"]


async def _put(url: str, body: bytes, content_type: str) -> None:
    async with httpx.AsyncClient() as raw:
        response = await raw.put(url, content=body, headers={"Content-Type": content_type})
        assert response.status_code == 200, response.text


async def test_oversized_upload_is_rejected_and_the_slot_returned(
    client: AsyncClient, future: datetime
) -> None:
    code, _ = await make_film(client, closes_at=future, reveal_at=future, shot_limit=3)
    token = await join(client, code)

    shot_id, url = await _reserve(client, code, token)
    oversized = b"\xff\xd8\xff" + b"\x00" * (get_settings().max_upload_bytes + 1024)
    await _put(url, oversized, "image/jpeg")

    committed = await client.post(
        f"/v1/films/{code}/shots/{shot_id}/commit", headers=auth(token)
    )
    assert committed.status_code == 413, committed.text

    # The slot goes back, otherwise one fat upload would cost a guest a photo.
    reserved_again = await client.post(
        f"/v1/films/{code}/shots/reserve",
        json={"shot_id": str(uuid.uuid4())},
        headers=auth(token),
    )
    assert reserved_again.json()["shots_remaining"] == 2


async def test_oversized_upload_does_not_linger_in_storage(
    client: AsyncClient, future: datetime
) -> None:
    """Storage is billed by the byte, so a rejected upload must not survive."""
    from app.services import storage

    code, _ = await make_film(client, closes_at=future, reveal_at=future)
    token = await join(client, code)
    shot_id, url = await _reserve(client, code, token)

    await _put(url, b"\xff\xd8\xff" + b"\x00" * (get_settings().max_upload_bytes + 1), "image/jpeg")
    await client.post(f"/v1/films/{code}/shots/{shot_id}/commit", headers=auth(token))

    reserved = await client.post(
        f"/v1/films/{code}/shots/reserve",
        json={"shot_id": shot_id},
        headers=auth(token),
    )
    key = reserved.json()["storage_key"]
    assert await storage.object_exists(key) is False


async def test_non_image_upload_is_rejected(client: AsyncClient, future: datetime) -> None:
    code, _ = await make_film(client, closes_at=future, reveal_at=future)
    token = await join(client, code)

    shot_id = str(uuid.uuid4())
    reserved = await client.post(
        f"/v1/films/{code}/shots/reserve",
        json={"shot_id": shot_id, "content_type": "video/mp4"},
        headers=auth(token),
    )
    assert reserved.status_code == 200
    await _put(reserved.json()["upload_url"], b"not a photo", "video/mp4")

    committed = await client.post(
        f"/v1/films/{code}/shots/{shot_id}/commit", headers=auth(token)
    )
    assert committed.status_code == 415, committed.text


async def test_expired_shot_cannot_be_committed_later(
    client: AsyncClient, future: datetime
) -> None:
    """The cap bypass this guard exists to prevent.

    A rejected upload hands the slot back. If the same shot id could then be
    committed, a guest would hold both the replacement slot and the original
    photo, shooting past the limit one rejected upload at a time.
    """
    code, _ = await make_film(client, closes_at=future, reveal_at=future, shot_limit=2)
    token = await join(client, code)

    shot_id, url = await _reserve(client, code, token)
    await _put(url, b"\xff\xd8\xff" + b"\x00" * (get_settings().max_upload_bytes + 1), "image/jpeg")
    rejected = await client.post(
        f"/v1/films/{code}/shots/{shot_id}/commit", headers=auth(token)
    )
    assert rejected.status_code == 413

    # Re-upload something perfectly valid to the same key and try again.
    again = await client.post(
        f"/v1/films/{code}/shots/reserve",
        json={"shot_id": shot_id},
        headers=auth(token),
    )
    await _put(again.json()["upload_url"], TINY_JPEG, "image/jpeg")

    resurrected = await client.post(
        f"/v1/films/{code}/shots/{shot_id}/commit", headers=auth(token)
    )
    assert resurrected.status_code == 409, "an expired shot must not come back to life"

    gallery = await client.get(f"/v1/films/{code}/gallery")
    assert gallery.json()["shot_count"] == 0


async def test_a_normal_photo_still_commits(client: AsyncClient, future: datetime) -> None:
    """The guard rails must not have broken the ordinary path."""
    code, _ = await make_film(client, closes_at=future, reveal_at=future)
    token = await join(client, code)

    shot_id, url = await _reserve(client, code, token)
    await _put(url, TINY_JPEG, "image/jpeg")

    committed = await client.post(
        f"/v1/films/{code}/shots/{shot_id}/commit", headers=auth(token)
    )
    assert committed.status_code == 200, committed.text
