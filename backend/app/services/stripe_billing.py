"""Talk to Stripe, or pretend to.

The catalog never lives in the Stripe dashboard. Every session is built with
``price_data`` from ``app.services.catalog`` so a price change is a deploy.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any

import stripe

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import Film
from app.services.billing import CheckoutNotConfigured
from app.services.catalog import CURRENCY, Addon, Tier

log = get_logger(__name__)


class StripeError(Exception):
    pass


class BadWebhookSignature(StripeError):
    pass


def create_checkout_session(
    *,
    film: Film,
    kind: str,
    amount_cents: int,
    description: str,
    guest_cap: int | None,
    addon_id: str | None,
) -> tuple[str, str, bool]:
    """Return ``(session_id, url, fake)``."""
    settings = get_settings()
    success = f"{settings.public_web_url.rstrip('/')}/f/{film.code}/host?checkout=success"
    cancel = f"{settings.public_web_url.rstrip('/')}/f/{film.code}/host?checkout=cancel"

    if settings.use_fake_billing:
        session_id = f"cs_fake_{uuid.uuid4().hex}"
        log.info(
            "billing.checkout_fake",
            film_id=str(film.id),
            kind=kind,
            amount_cents=amount_cents,
        )
        return session_id, success, True

    if not settings.stripe_configured:
        raise CheckoutNotConfigured("stripe is not configured")

    metadata = {
        "film_id": str(film.id),
        "film_code": film.code,
        "kind": kind,
        "guest_cap": "" if guest_cap is None else str(guest_cap),
        "addon_id": addon_id or "",
    }
    params: dict[str, Any] = {
        "mode": "payment",
        "success_url": success,
        "cancel_url": cancel,
        "client_reference_id": str(film.id),
        "metadata": metadata,
        "line_items": [
            {
                "quantity": 1,
                "price_data": {
                    "currency": CURRENCY,
                    "unit_amount": amount_cents,
                    "product_data": {"name": description, "metadata": metadata},
                },
            }
        ],
        # The host types an email on Stripe's page. That is the receipt; we do
        # not have host accounts yet, so we cannot prefill it.
        "billing_address_collection": "auto",
    }
    if settings.stripe_automatic_tax:
        params["automatic_tax"] = {"enabled": True}
        # Stripe cannot pick a jurisdiction without one, and a wrong VAT rate is
        # the host's problem to unwind, not ours.
        params["billing_address_collection"] = "required"
        # A company buying a staff party needs its VAT number on the invoice to
        # reclaim the tax; without this they have to ask support for a reissue.
        params["tax_id_collection"] = {"enabled": True}
        line_item = params["line_items"][0]
        line_item["price_data"]["tax_behavior"] = settings.stripe_tax_behavior

    stripe.api_key = settings.stripe_secret_key
    try:
        created = stripe.checkout.Session.create(**params)
    except stripe.StripeError as exc:
        raise StripeError(str(exc)) from exc

    url = created.url
    if not created.id or not url:
        raise StripeError("stripe returned an empty checkout session")
    log.info(
        "billing.checkout_created",
        film_id=str(film.id),
        session_id=created.id,
        amount_cents=amount_cents,
    )
    return created.id, url, False


def fetch_receipt_url(payment_intent_id: str) -> str | None:
    """Stripe hosts the receipt; the URL only exists on the charge.

    Called once at fulfillment rather than on every host page view, and never
    on the fake path, where there is no charge to look up. A failure here is
    logged and swallowed: a missing receipt link must not fail a paid webhook,
    or Stripe will retry a payment we already granted.
    """
    settings = get_settings()
    if settings.use_fake_billing or not settings.stripe_configured:
        return None

    stripe.api_key = settings.stripe_secret_key
    try:
        intent = stripe.PaymentIntent.retrieve(payment_intent_id, expand=["latest_charge"])
    except stripe.StripeError as exc:
        log.warning(
            "billing.receipt_lookup_failed", payment_intent=payment_intent_id, error=str(exc)
        )
        return None

    charge = intent.latest_charge
    # Expanded, this is a Charge object; unexpanded it is a bare id string.
    url = getattr(charge, "receipt_url", None)
    return str(url) if url else None


def parse_webhook(payload: bytes, signature: str) -> dict[str, Any]:
    settings = get_settings()
    secret = settings.stripe_webhook_secret
    if not secret:
        raise CheckoutNotConfigured("stripe webhook secret is not configured")
    try:
        event = stripe.Webhook.construct_event(payload, signature, secret)
    except stripe.SignatureVerificationError as exc:
        raise BadWebhookSignature(str(exc)) from None
    except ValueError as exc:
        raise BadWebhookSignature(str(exc)) from None
    if isinstance(event, dict):
        return event
    to_dict = getattr(event, "to_dict", None)
    if callable(to_dict):
        result: dict[str, Any] = to_dict()
        return result
    raise BadWebhookSignature("unreadable stripe event")


def sign_payload(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    """Build a Stripe-Signature header. Used by tests, not by production."""
    ts = int(time.time()) if timestamp is None else timestamp
    signed = f"{ts}.".encode() + payload
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


def checkout_completed_payload(
    *,
    session_id: str,
    payment_intent: str = "pi_test",
    amount_total: int | None = None,
    amount_tax: int = 0,
    customer_email: str | None = None,
) -> bytes:
    """A minimal ``checkout.session.completed`` body for tests."""
    body = {
        "id": f"evt_{uuid.uuid4().hex}",
        "object": "event",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": session_id,
                "object": "checkout.session",
                "payment_status": "paid",
                "payment_intent": payment_intent,
                "amount_total": amount_total,
                "total_details": {"amount_tax": amount_tax},
                "customer_details": {"email": customer_email},
            }
        },
    }
    return json.dumps(body, separators=(",", ":")).encode()


def charge_refunded_payload(
    *,
    payment_intent: str = "pi_test",
    amount_refunded: int,
    refunded: bool = True,
    receipt_url: str | None = None,
) -> bytes:
    """A minimal ``charge.refunded`` body for tests."""
    body = {
        "id": f"evt_{uuid.uuid4().hex}",
        "object": "event",
        "type": "charge.refunded",
        "data": {
            "object": {
                "id": f"ch_{uuid.uuid4().hex}",
                "object": "charge",
                "payment_intent": payment_intent,
                "amount_refunded": amount_refunded,
                "refunded": refunded,
                "receipt_url": receipt_url,
            }
        },
    }
    return json.dumps(body, separators=(",", ":")).encode()


def describe_purchase(*, tier: Tier | None, addon: Addon | None) -> str:
    if tier is not None:
        return f"Filmroll — {tier.label}"
    if addon is not None:
        return f"Filmroll — {addon.label}"
    raise StripeError("nothing to describe")
