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
from app.services.stripe_billing import (
    charge_refunded_payload,
    checkout_completed_payload,
    sign_payload,
)
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
    assert any(addon["id"] == "unlimited_shots" for addon in body["addons"])


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
    response = await client.patch(f"/v1/films/{code}", json={"guest_cap": 50}, headers=auth(host))
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


async def _open_payment(code: str, session_id: str, *, amount_cents: int = 2900) -> None:
    """Insert the row Session.create would have left behind."""
    async with get_sessionmaker()() as session:
        film = await session.scalar(select(Film).where(Film.code == code.upper()))
        assert film is not None
        session.add(
            Payment(
                film_id=film.id,
                provider="stripe",
                provider_session_id=session_id,
                kind="tier:g25",
                guest_cap=25,
                amount_cents=amount_cents,
                currency="usd",
                status="open",
            )
        )
        await session.commit()


async def test_payments_lists_receipts_for_the_host(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future, guest_cap=5)
    await client.post(f"/v1/films/{code}/checkout", json={"tier_id": "g25"}, headers=auth(host))
    await client.post(
        f"/v1/films/{code}/checkout", json={"addon_id": "keep_forever"}, headers=auth(host)
    )

    response = await client.get(f"/v1/films/{code}/payments", headers=auth(host))
    assert response.status_code == 200, response.text
    body = response.json()

    kinds = {row["kind"] for row in body["payments"]}
    assert kinds == {"tier:g25", "addon:keep_forever"}
    assert all(row["status"] == "paid" for row in body["payments"])
    # Fake Checkout moves no money, so the total is the catalog price and no tax.
    assert body["total_paid_cents"] == 2900 + 3900
    assert body["total_tax_cents"] == 0
    assert body["total_refunded_cents"] == 0

    labels = {row["label"] for row in body["payments"]}
    assert labels == {"25 guests", "Keep photos forever"}


async def test_guest_cannot_read_payments(client: AsyncClient, future: datetime) -> None:
    code, _ = await make_film(client, closes_at=future, reveal_at=future, guest_cap=5)
    guest = await join(client, code)
    response = await client.get(f"/v1/films/{code}/payments", headers=auth(guest))
    assert response.status_code == 403


async def test_abandoned_checkout_is_not_a_receipt(client: AsyncClient, future: datetime) -> None:
    code, host = await make_film(client, closes_at=future, reveal_at=future, guest_cap=5)
    await _open_payment(code, "cs_test_abandoned")

    response = await client.get(f"/v1/films/{code}/payments", headers=auth(host))
    assert response.status_code == 200
    assert response.json()["payments"] == []


async def test_webhook_records_tax_and_customer_email(
    client: AsyncClient, future: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "whsec_test_tax"
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", secret)
    code, host = await make_film(client, closes_at=future, reveal_at=future, guest_cap=5)
    await _open_payment(code, "cs_test_tax_1")

    payload = checkout_completed_payload(
        session_id="cs_test_tax_1",
        payment_intent="pi_tax_1",
        amount_total=3_480,
        amount_tax=580,
        customer_email="host@example.com",
    )
    accepted = await client.post(
        "/v1/billing/webhook",
        content=payload,
        headers={"stripe-signature": sign_payload(payload, secret)},
    )
    assert accepted.status_code == 200, accepted.text

    body = (await client.get(f"/v1/films/{code}/payments", headers=auth(host))).json()
    receipt = body["payments"][0]
    # The catalog price and the captured total differ by exactly the VAT.
    assert receipt["amount_cents"] == 2900
    assert receipt["tax_cents"] == 580
    assert receipt["total_cents"] == 3480
    assert receipt["customer_email"] == "host@example.com"
    assert body["total_tax_cents"] == 580


async def test_refund_is_recorded_without_lowering_the_cap(
    client: AsyncClient, future: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "whsec_test_refund"
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", secret)
    code, host = await make_film(client, closes_at=future, reveal_at=future, guest_cap=5)
    await _open_payment(code, "cs_test_refund_1")

    paid = checkout_completed_payload(
        session_id="cs_test_refund_1", payment_intent="pi_refund_1", amount_total=2900
    )
    await client.post(
        "/v1/billing/webhook",
        content=paid,
        headers={"stripe-signature": sign_payload(paid, secret)},
    )
    assert (await client.get(f"/v1/films/{code}")).json()["entitled_guest_cap"] == 25

    refund = charge_refunded_payload(payment_intent="pi_refund_1", amount_refunded=2900)
    response = await client.post(
        "/v1/billing/webhook",
        content=refund,
        headers={"stripe-signature": sign_payload(refund, secret)},
    )
    assert response.status_code == 200, response.text

    # Guests already in the room keep their seats; the refund is bookkeeping.
    film = (await client.get(f"/v1/films/{code}")).json()
    assert film["entitled_guest_cap"] == 25

    body = (await client.get(f"/v1/films/{code}/payments", headers=auth(host))).json()
    receipt = body["payments"][0]
    assert receipt["status"] == "refunded"
    assert receipt["refunded_cents"] == 2900
    assert receipt["refunded_at"]
    assert body["total_refunded_cents"] == 2900


async def test_partial_refund_keeps_the_payment_paid(
    client: AsyncClient, future: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "whsec_test_partial"
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", secret)
    code, host = await make_film(client, closes_at=future, reveal_at=future, guest_cap=5)
    await _open_payment(code, "cs_test_partial_1")

    paid = checkout_completed_payload(
        session_id="cs_test_partial_1", payment_intent="pi_partial_1", amount_total=2900
    )
    await client.post(
        "/v1/billing/webhook",
        content=paid,
        headers={"stripe-signature": sign_payload(paid, secret)},
    )

    refund = charge_refunded_payload(
        payment_intent="pi_partial_1", amount_refunded=900, refunded=False
    )
    await client.post(
        "/v1/billing/webhook",
        content=refund,
        headers={"stripe-signature": sign_payload(refund, secret)},
    )

    body = (await client.get(f"/v1/films/{code}/payments", headers=auth(host))).json()
    receipt = body["payments"][0]
    assert receipt["status"] == "paid"
    assert receipt["refunded_cents"] == 900
    assert body["total_refunded_cents"] == 900


async def test_refund_for_an_unknown_payment_is_ignored(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "whsec_test_unknown_refund"
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", secret)
    refund = charge_refunded_payload(payment_intent="pi_never_seen", amount_refunded=100)
    response = await client.post(
        "/v1/billing/webhook",
        content=refund,
        headers={"stripe-signature": sign_payload(refund, secret)},
    )
    assert response.status_code == 200
