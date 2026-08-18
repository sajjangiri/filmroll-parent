"""Entitlements: apply a paid tier or add-on to a film.

Checkout (real or fake) always lands here. The webhook is just another caller
with a Stripe signature around the same session id. That is what makes the fake
local path and the production path the same state machine.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Film, Payment
from app.services.catalog import (
    KEEP_FOREVER,
    Addon,
    Tier,
    addon_by_id,
    price_for_cap,
    tier_by_id,
)

log = get_logger(__name__)


class BillingError(Exception):
    pass


class AlreadyEntitled(BillingError):
    pass


class AlreadyPurchased(BillingError):
    pass


class CheckoutNotConfigured(BillingError):
    pass


def quote_tier(film: Film, tier: Tier) -> int:
    """Cents to charge to move this film onto ``tier``.

    Upgrades are the difference between catalog prices, not a second full
    ticket. Buying 50 after 25 costs $20, not $49.
    """
    if tier.amount_cents <= 0:
        raise AlreadyEntitled("the free tier is already included")
    if tier.guest_cap <= film.entitled_guest_cap:
        raise AlreadyEntitled(f"already entitled to {film.entitled_guest_cap} guests")
    delta = tier.amount_cents - price_for_cap(film.entitled_guest_cap)
    if delta <= 0:
        raise AlreadyEntitled(f"already entitled to {film.entitled_guest_cap} guests")
    return delta


def quote_addon(film: Film, addon: Addon) -> int:
    if addon.id == KEEP_FOREVER.id and film.keep_forever:
        raise AlreadyPurchased("this film already keeps photos forever")
    return addon.amount_cents


def resolve_item(tier_id: str | None, addon_id: str | None) -> tuple[Tier | None, Addon | None]:
    if bool(tier_id) == bool(addon_id):
        raise BillingError("choose a tier or an add-on, not both")
    if tier_id:
        return tier_by_id(tier_id), None
    return None, addon_by_id(addon_id or "")


def kind_for(*, tier: Tier | None, addon: Addon | None) -> str:
    if tier is not None:
        return f"tier:{tier.id}"
    if addon is not None:
        return f"addon:{addon.id}"
    raise BillingError("choose a tier or an add-on")


async def open_payment(
    session: AsyncSession,
    *,
    film: Film,
    provider_session_id: str,
    kind: str,
    guest_cap: int | None,
    amount_cents: int,
    currency: str,
) -> Payment:
    payment = Payment(
        film_id=film.id,
        provider="stripe",
        provider_session_id=provider_session_id,
        kind=kind,
        guest_cap=guest_cap,
        amount_cents=amount_cents,
        currency=currency,
        status="open",
    )
    session.add(payment)
    await session.flush()
    return payment


async def payment_by_session(session: AsyncSession, provider_session_id: str) -> Payment | None:
    result = await session.execute(
        select(Payment).where(Payment.provider_session_id == provider_session_id)
    )
    return result.scalar_one_or_none()


async def fulfill_session(
    session: AsyncSession,
    *,
    provider_session_id: str,
    provider_payment_id: str | None = None,
) -> Payment:
    """Mark a session paid and grant the entitlement.

    Safe to call twice with the same session id: the second call is a no-op.
    Stripe retries webhooks; fake Checkout calls this inline.
    """
    payment = await payment_by_session(session, provider_session_id)
    if payment is None:
        raise BillingError(f"unknown checkout session {provider_session_id}")

    if payment.status == "paid":
        return payment

    film = await session.get(Film, payment.film_id)
    if film is None:
        raise BillingError(f"film missing for payment {payment.id}")

    _grant(film, payment)
    payment.status = "paid"
    payment.paid_at = datetime.now(UTC)
    if provider_payment_id:
        payment.provider_payment_id = provider_payment_id
    await session.flush()
    log.info(
        "billing.paid",
        film_id=str(film.id),
        session_id=provider_session_id,
        kind=payment.kind,
        amount_cents=payment.amount_cents,
        entitled_guest_cap=film.entitled_guest_cap,
        keep_forever=film.keep_forever,
    )
    return payment


def _grant(film: Film, payment: Payment) -> None:
    prefix, _, item_id = payment.kind.partition(":")
    if prefix == "tier":
        cap = payment.guest_cap
        if cap is None:
            cap = tier_by_id(item_id).guest_cap
        # Entitlement first so the check constraint never sees a cap above it.
        film.entitled_guest_cap = max(film.entitled_guest_cap, cap)
        film.guest_cap = max(film.guest_cap, cap)
        return
    if prefix == "addon" and item_id == KEEP_FOREVER.id:
        film.keep_forever = True
        return
    raise BillingError(f"unknown purchase {payment.kind}")


async def mark_refunded(session: AsyncSession, *, provider_payment_id: str) -> Payment | None:
    """Record a refund without lowering the cap.

    Guests who already joined cannot be un-invited by a chargeback. The host
    ZIP is also always free. A refunded payment is an accounting fact, not a
    capacity change.
    """
    result = await session.execute(
        select(Payment).where(Payment.provider_payment_id == provider_payment_id)
    )
    payment = result.scalar_one_or_none()
    if payment is None:
        return None
    if payment.status != "refunded":
        payment.status = "refunded"
        await session.flush()
        log.info(
            "billing.refunded",
            film_id=str(payment.film_id),
            payment_id=str(payment.id),
            amount_cents=payment.amount_cents,
        )
    return payment
