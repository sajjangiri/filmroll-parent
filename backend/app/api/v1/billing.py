from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import DbSession
from app.core.logging import get_logger
from app.schemas import BillingAddon, BillingTier, CatalogResponse
from app.services import billing, stripe_billing
from app.services.catalog import (
    ADDONS,
    CURRENCY,
    FREE_GUEST_CAP,
    STORAGE_INCLUDED_DAYS,
    TIERS,
)

router = APIRouter(prefix="/v1/billing", tags=["billing"])
log = get_logger(__name__)


@router.get("/catalog", response_model=CatalogResponse)
async def catalog() -> CatalogResponse:
    return CatalogResponse(
        free_guest_cap=FREE_GUEST_CAP,
        storage_days=STORAGE_INCLUDED_DAYS,
        currency=CURRENCY,
        tiers=[
            BillingTier(
                id=tier.id,
                guest_cap=tier.guest_cap,
                amount_cents=tier.amount_cents,
                currency=CURRENCY,
                label=tier.label,
            )
            for tier in TIERS
        ],
        addons=[
            BillingAddon(
                id=addon.id,
                amount_cents=addon.amount_cents,
                currency=CURRENCY,
                label=addon.label,
            )
            for addon in ADDONS
        ],
    )


@router.post("/webhook")
async def stripe_webhook(request: Request, session: DbSession) -> dict[str, str]:
    """Stripe sends this. Signatures are verified; the body is never trusted raw.

    Unknown session ids return 200 so a webhook from another Stripe account
    does not sit in a retry loop. Fulfillment itself is idempotent.
    """
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        event = stripe_billing.parse_webhook(payload, signature)
    except stripe_billing.BadWebhookSignature:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid stripe signature") from None
    except billing.CheckoutNotConfigured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "billing is not configured"
        ) from None

    event_type = str(event.get("type", ""))
    data = event.get("data", {}).get("object") or {}

    if event_type == "checkout.session.completed":
        if data.get("payment_status") != "paid":
            return {"status": "ignored"}
        session_id = str(data.get("id") or "")
        payment_intent = data.get("payment_intent")
        if isinstance(payment_intent, dict):
            payment_intent = payment_intent.get("id")
        try:
            await billing.fulfill_session(
                session,
                provider_session_id=session_id,
                provider_payment_id=str(payment_intent) if payment_intent else None,
            )
        except billing.BillingError as exc:
            log.warning("billing.webhook_unknown_session", session_id=session_id, error=str(exc))
            return {"status": "ignored"}
        return {"status": "ok"}

    if event_type == "charge.refunded":
        payment_intent = data.get("payment_intent")
        if isinstance(payment_intent, dict):
            payment_intent = payment_intent.get("id")
        if payment_intent:
            await billing.mark_refunded(session, provider_payment_id=str(payment_intent))
        return {"status": "ok"}

    return {"status": "ignored"}
