"""Billing: free cap, entitlements, Checkout, webhooks.

The guest cap is the price. A PATCH cannot raise it; only a paid session can.
Local tests use fake Checkout so the suite does not need a Stripe key. The
webhook path is exercised with a locally signed payload against an open payment
row, which is the same state production has after Session.create.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Film, Payment
from app.db.session import get_sessionmaker
from app.services.catalog import FREE_GUEST_CAP
from app.services.stripe_billing import checkout_completed_payload, sign_payload
from tests.conftest import auth, join, make_film

pytestmark = pytest.mark.integration


async def test_catalog_is_public(client: AsyncClient) -> None:
    response = await client.get("/v1/billing/catalog")
    assert response.status_code == 200
    body = response.json()
    assert body["free_guest_cap"] == FREE_GUEST_CAP
    assert body["tiers"][0]["id"] == "free"
    assert body["tiers"][0]["amount_cents"] == 0
    assert any(tier["id"] == "g50" and tier["guest_cap"] == 50 for tier in body["tiers"])
    assert any(addon["id"] == "keep_forever" for addon in body["addons"])


async def test_create_clamps_to_the_free_guest_cap(client: AsyncClient, future: datetime) -> None:
    response = await client.post(
        "/v1/films",
        json={
            "title": "Big wedding",
            "event_type": "wedding",
            "closes_at": future.isoformat(),
            "reveal_at": future.isoformat(),
            "shot_limit": 8,
            "guest_cap": 250,
        },
    )
    assert response.status_code == 201, response.text
    film = response.json()["film"]
    assert film["guest_cap"] == FREE_GUEST_CAP
    assert film["entitled_guest_cap"] == FREE_GUEST_CAP
    assert film["keep_forever"] is False
    assert film["storage_until"]


async def test_cannot_raise_the_cap_without_paying(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future, guest_cap=5)
    response = await client.patch(
        f"/v1/films/{code}", json={"guest_cap": 50}, headers=auth(host)
    )
    assert response.status_code == 402


async def test_fake_checkout_raises_the_guest_cap(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future, guest_cap=5)
    paid = await client.post(
        f"/v1/films/{code}/checkout", json={"tier_id": "g50"}, headers=auth(host)
    )
    assert paid.status_code == 200, paid.text
    body = paid.json()
    assert body["fake"] is True
    assert body["amount_cents"] == 4900
    assert "checkout=success" in body["url"]

    film = (await client.get(f"/v1/films/{code}")).json()
    assert film["guest_cap"] == 50
    assert film["entitled_guest_cap"] == 50


async def test_upgrade_charges_the_price_delta(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future, guest_cap=5)
    first = await client.post(
        f"/v1/films/{code}/checkout", json={"tier_id": "g25"}, headers=auth(host)
    )
    assert first.json()["amount_cents"] == 2900

    second = await client.post(
        f"/v1/films/{code}/checkout", json={"tier_id": "g50"}, headers=auth(host)
    )
    assert second.status_code == 200, second.text
    assert second.json()["amount_cents"] == 2000

    film = (await client.get(f"/v1/films/{code}")).json()
    assert film["entitled_guest_cap"] == 50


async def test_cannot_buy_a_lower_or_same_tier(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future, guest_cap=5)
    await client.post(f"/v1/films/{code}/checkout", json={"tier_id": "g50"}, headers=auth(host))
    again = await client.post(
        f"/v1/films/{code}/checkout", json={"tier_id": "g25"}, headers=auth(host)
    )
    assert again.status_code == 409
    free = await client.post(
        f"/v1/films/{code}/checkout", json={"tier_id": "free"}, headers=auth(host)
    )
    assert free.status_code == 409


async def test_keep_forever_is_a_one_time_add_on(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future, guest_cap=5)
    paid = await client.post(
        f"/v1/films/{code}/checkout",
        json={"addon_id": "keep_forever"},
        headers=auth(host),
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["amount_cents"] == 3900
    film = (await client.get(f"/v1/films/{code}")).json()
    assert film["keep_forever"] is True

    again = await client.post(
        f"/v1/films/{code}/checkout",
        json={"addon_id": "keep_forever"},
        headers=auth(host),
    )
    assert again.status_code == 409


async def test_guest_cannot_start_checkout(client: AsyncClient, future: datetime) -> None:
    code, _ = await make_film(client, closes_at=future, reveal_at=future, guest_cap=5)
    guest = await join(client, code)
    response = await client.post(
        f"/v1/films/{code}/checkout", json={"tier_id": "g25"}, headers=auth(guest)
    )
    assert response.status_code == 403


async def test_signed_webhook_grants_entitlement_and_is_idempotent(
    client: AsyncClient, future: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "whsec_test_webhook_secret"
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", secret)
    code, _ = await make_film(client, closes_at=future, reveal_at=future, guest_cap=5)

    async with get_sessionmaker()() as session:
        film = await session.scalar(select(Film).where(Film.code == code.upper()))
        assert film is not None
        session.add(
            Payment(
                film_id=film.id,
                provider="stripe",
                provider_session_id="cs_test_webhook_1",
                kind="tier:g25",
                guest_cap=25,
                amount_cents=2900,
                currency="usd",
                status="open",
            )
        )
        await session.commit()

    payload = checkout_completed_payload(session_id="cs_test_webhook_1")
    header = sign_payload(payload, secret)
    first = await client.post(
        "/v1/billing/webhook", content=payload, headers={"stripe-signature": header}
    )
    assert first.status_code == 200, first.text

    film = (await client.get(f"/v1/films/{code}")).json()
    assert film["guest_cap"] == 25
    assert film["entitled_guest_cap"] == 25

    replay = await client.post(
        "/v1/billing/webhook", content=payload, headers={"stripe-signature": header}
    )
    assert replay.status_code == 200
    film = (await client.get(f"/v1/films/{code}")).json()
    assert film["guest_cap"] == 25


async def test_webhook_rejects_a_bad_signature(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "whsec_real")
    payload = checkout_completed_payload(session_id="cs_test_nope")
    response = await client.post(
        "/v1/billing/webhook",
        content=payload,
        headers={"stripe-signature": "t=1,v1=deadbeef"},
    )
    assert response.status_code == 400
