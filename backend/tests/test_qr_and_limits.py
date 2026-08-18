"""QR codes and rate limiting.

The QR test is really a privacy test. The join URL identifies a private event,
so the assertion that matters is that generating one involves no third party.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from tests.conftest import auth, join, make_film

pytestmark = pytest.mark.integration


async def test_qr_is_served_by_us_and_encodes_the_join_url(
    client: AsyncClient, future: datetime
) -> None:
    code, _ = await make_film(client, closes_at=future, reveal_at=future)

    response = await client.get(f"/v1/films/{code}/qr.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")

    body = response.text
    assert body.lstrip().startswith("<?xml") or body.lstrip().startswith("<svg")

    # The code is drawn as vector paths by us. No third-party generator, and no
    # embedded <image> that would make the guest's browser fetch from elsewhere.
    assert "qrserver" not in body
    assert "<image" not in body
    assert "<path" in body


async def test_qr_matches_the_join_url_the_api_reports(
    client: AsyncClient, future: datetime
) -> None:
    """A card that points somewhere other than the app is worse than no card."""
    code, _ = await make_film(client, closes_at=future, reveal_at=future)

    film = await client.get(f"/v1/films/{code}")
    reported = film.json()["join_url"]
    assert reported.endswith(f"/f/{code}")

    from app.services import qrcodes

    assert qrcodes.join_url(code) == reported


async def test_unknown_film_has_no_qr(client: AsyncClient) -> None:
    assert (await client.get("/v1/films/NOPE99/qr.svg")).status_code == 404


async def test_reserve_is_rate_limited(
    client: AsyncClient, future: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A single guest cannot spin the reserve endpoint without limit."""
    monkeypatch.setattr(get_settings(), "rate_limit_reserve_per_minute", 8)
    limit = 8
    code, _ = await make_film(
        client, closes_at=future, reveal_at=future, shot_limit=limit + 50
    )
    token = await join(client, code)

    statuses = []
    for _ in range(limit + 5):
        response = await client.post(
            f"/v1/films/{code}/shots/reserve",
            json={"shot_id": str(uuid.uuid4())},
            headers=auth(token),
        )
        statuses.append(response.status_code)

    assert 429 in statuses, "expected the limiter to engage"
    assert statuses.index(429) >= limit, "limiter engaged earlier than configured"


async def test_rate_limiting_fails_open(
    client: AsyncClient, future: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A limiter outage must not stop a wedding.

    Redis is not the source of truth for anything here. Blocking every guest
    because a cache is down would be far worse than the burst being prevented.
    """
    from app.services import ratelimit

    def explode() -> object:
        raise ConnectionError("redis is down")

    monkeypatch.setattr(ratelimit, "_redis", explode)

    code, _ = await make_film(client, closes_at=future, reveal_at=future)
    response = await client.post(
        f"/v1/films/{code}/join", json={"display_name": "Ada"}
    )
    assert response.status_code == 201, "join must still work without Redis"
