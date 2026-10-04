"""What a film can cost.

The catalog is code, not a Stripe Product dashboard. Checkout always sends
``price_data`` built from these rows, so a price change is a deploy rather than
a console click that the API might disagree with.

We charge for **capacity**, never per shutter press. A guest taking their eighth
photo is not a revenue event; a host raising the room from 5 to 50 is.
"""

from __future__ import annotations

from dataclasses import dataclass

FREE_GUEST_CAP = 5
STORAGE_INCLUDED_DAYS = 365
CURRENCY = "usd"


@dataclass(frozen=True, slots=True)
class Tier:
    id: str
    guest_cap: int
    amount_cents: int
    label: str


@dataclass(frozen=True, slots=True)
class Addon:
    id: str
    amount_cents: int
    label: str


# Ladder is inclusive: paying for 50 covers 50 guests, not "up to 49 plus you".
TIERS: tuple[Tier, ...] = (
    Tier("free", FREE_GUEST_CAP, 0, "5 guests"),
    Tier("g25", 25, 2_900, "25 guests"),
    Tier("g50", 50, 4_900, "50 guests"),
    Tier("g100", 100, 8_900, "100 guests"),
    Tier("g150", 150, 12_900, "150 guests"),
    Tier("g250", 250, 17_900, "250 guests"),
)

KEEP_FOREVER = Addon("keep_forever", 3_900, "Keep photos forever")
UNLIMITED_SHOTS = Addon("unlimited_shots", 1_900, "Unlimited shots per guest")
VIDEO_PACK = Addon("video_pack", 1_900, "Video clips (3 per guest, up to 15 s)")

ADDONS: tuple[Addon, ...] = (KEEP_FOREVER, UNLIMITED_SHOTS, VIDEO_PACK)

# What the video pack buys. A separate allowance from the photo roll, so a clip
# never costs a guest one of their photos. The worker trims anything longer than
# CLIP_MAX_SECONDS, which is the real cap; clients stop recording there too.
CLIPS_PER_GUEST = 3
CLIP_MAX_SECONDS = 15


class CatalogError(Exception):
    pass


class UnknownTier(CatalogError):
    pass


class UnknownAddon(CatalogError):
    pass


def tier_by_id(tier_id: str) -> Tier:
    for tier in TIERS:
        if tier.id == tier_id:
            return tier
    raise UnknownTier(tier_id)


def addon_by_id(addon_id: str) -> Addon:
    for addon in ADDONS:
        if addon.id == addon_id:
            return addon
    raise UnknownAddon(addon_id)


def price_for_cap(guest_cap: int) -> int:
    """Amount already paid for this entitlement, from the catalog.

    Entitlements land on exact tier caps, so a film entitled to 25 has paid
    $29, not a pro-rata. Free (cap 5 or below) has paid nothing.
    """
    paid = 0
    for tier in TIERS:
        if tier.guest_cap <= guest_cap:
            paid = tier.amount_cents
    return paid


def tier_covering(guest_cap: int) -> Tier:
    """Smallest tier that can host this many guests."""
    for tier in TIERS:
        if tier.guest_cap >= guest_cap:
            return tier
    raise UnknownTier(f"no tier covers {guest_cap} guests")


def paid_tiers() -> tuple[Tier, ...]:
    return tuple(tier for tier in TIERS if tier.amount_cents > 0)


def describe_kind(kind: str) -> str:
    """Human label for a stored ``tier:g50`` / ``addon:keep_forever`` string.

    Falls back to the raw kind rather than raising: a receipt for a tier we have
    since renamed still has to render on the host's history.
    """
    prefix, _, item_id = kind.partition(":")
    try:
        if prefix == "tier":
            return tier_by_id(item_id).label
        if prefix == "addon":
            return addon_by_id(item_id).label
    except CatalogError:
        return kind
    return kind
