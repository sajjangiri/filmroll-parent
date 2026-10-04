"""Optional join PIN.

A QR card sits on a table all evening. Anyone who photographs it — a passing
guest at the next wedding, someone who saw it on social media — can join the
film and start shooting into somebody's private event. The PIN is the answer to
that, and only that.

Why a keyed hash rather than bcrypt or Argon2. The secret being protected has
at most a million candidates, so no work factor makes an offline guess hard;
what makes it hard is that the digest is an HMAC under ``SECRET_KEY``, which is
not in the database. An attacker holding a database dump cannot test candidate
PINs without also holding the application secret, and an attacker who *does*
hold that secret can mint guest tokens outright and has no use for the PIN. The
online attacker, who is the one this feature actually exists to stop, is bounded
by the join rate limiter instead.
"""

from __future__ import annotations

import hashlib
import hmac
import re

from app.core.config import get_settings

# Digits only, so the guest sees a numeric keypad and a host can read it aloud
# across a room without spelling anything.
PIN_PATTERN = re.compile(r"^\d{4,8}$")


class InvalidPin(Exception):
    pass


def normalize(pin: str) -> str:
    """Accept what a human types: spaces and dashes between the digits."""
    cleaned = re.sub(r"[\s-]", "", pin)
    if not PIN_PATTERN.match(cleaned):
        raise InvalidPin("a PIN must be 4 to 8 digits")
    return cleaned


def hash_pin(pin: str) -> str:
    return hmac.new(
        get_settings().secret_key.encode(), normalize(pin).encode(), hashlib.sha256
    ).hexdigest()


def matches(stored_hash: str | None, supplied: str | None) -> bool:
    """Whether ``supplied`` opens a film guarded by ``stored_hash``."""
    if stored_hash is None:
        return True
    if not supplied:
        return False
    try:
        candidate = hash_pin(supplied)
    except InvalidPin:
        # A malformed guess is a wrong guess, and saying so more precisely would
        # only tell an attacker what shape to try next.
        return False
    return hmac.compare_digest(stored_hash, candidate)
