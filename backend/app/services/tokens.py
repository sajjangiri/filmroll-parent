"""Guest and host tokens.

Guests never create accounts, which is the whole point of joining by QR. What
they get instead is a signed token scoped to one film and one guest identity:
no password, no email, no PII, but still something the server can authorise
against and that a device can persist.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt

from app.core.config import get_settings

ALGORITHM = "HS256"
Role = Literal["guest", "host", "cohost", "photographer"]

# Roles that hold a revocable seat row. "host" is the film creator, who has no
# seat and cannot be removed from their own film.
SeatRole = Literal["cohost", "photographer"]
SEAT_ROLES: frozenset[str] = frozenset({"cohost", "photographer"})
# Everyone who may open the host dashboard at all.
STAFF_ROLES: frozenset[str] = frozenset({"host", "cohost", "photographer"})
# Everyone who may change the film. A photographer may look, not touch.
STAFF_WRITE_ROLES: frozenset[str] = frozenset({"host", "cohost"})

# Long enough to outlive a wedding and the reveal that follows it.
GUEST_TOKEN_TTL = timedelta(days=30)
HOST_TOKEN_TTL = timedelta(days=365)
# Short on purpose. The long-lived host token is issued only after this is
# exchanged, so a forwarded inbox does not grant a year of access by itself.
MAGIC_TOKEN_TTL = timedelta(minutes=30)
# An invite is texted to a partner or emailed to a planner who may not set it up
# until the next day, so minutes are too short. The durable token is still only
# minted on claim, and revoking the seat kills every token cut from it.
SEAT_INVITE_TTL = timedelta(days=7)


class TokenError(Exception):
    pass


def _encode(claims: dict[str, object], ttl: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {**claims, "iat": now, "exp": now + ttl}
    return jwt.encode(payload, get_settings().secret_key, algorithm=ALGORITHM)


def issue_guest_token(film_id: uuid.UUID, guest_id: uuid.UUID) -> str:
    return _encode(
        {"role": "guest", "film_id": str(film_id), "sub": str(guest_id)},
        GUEST_TOKEN_TTL,
    )


def issue_host_token(film_id: uuid.UUID) -> str:
    return _encode({"role": "host", "film_id": str(film_id), "sub": str(film_id)}, HOST_TOKEN_TTL)


def issue_seat_token(film_id: uuid.UUID, seat_id: uuid.UUID, role: SeatRole) -> str:
    """Durable credential for a co-host or photographer.

    ``sub`` is the seat id rather than the film id, so every request can look
    the seat up and refuse a revoked one.
    """
    return _encode(
        {"role": role, "film_id": str(film_id), "sub": str(seat_id)},
        HOST_TOKEN_TTL,
    )


def issue_seat_invite(film_id: uuid.UUID, seat_id: uuid.UUID) -> str:
    return _encode(
        {
            "role": "magic",
            "purpose": "seat_claim",
            "film_id": str(film_id),
            "sub": str(seat_id),
        },
        SEAT_INVITE_TTL,
    )


def parse_seat_invite(token: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Return ``(film_id, seat_id)`` for a seat invite link."""
    claims = decode(token)
    if claims.get("role") != "magic" or claims.get("purpose") != "seat_claim":
        raise TokenError("not a seat invite")
    try:
        film_id = uuid.UUID(str(claims["film_id"]))
        seat_id = uuid.UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise TokenError("malformed claims") from exc
    return film_id, seat_id


def issue_magic_token(film_id: uuid.UUID, email: str) -> str:
    return _encode(
        {
            "role": "magic",
            "purpose": "host_login",
            "film_id": str(film_id),
            "email": email,
            "sub": str(film_id),
        },
        MAGIC_TOKEN_TTL,
    )


def parse_magic(token: str) -> tuple[uuid.UUID, str]:
    claims = decode(token)
    if claims.get("role") != "magic" or claims.get("purpose") != "host_login":
        raise TokenError("not a magic link")
    try:
        film_id = uuid.UUID(str(claims["film_id"]))
        email = str(claims["email"]).strip().lower()
    except (KeyError, ValueError) as exc:
        raise TokenError("malformed claims") from exc
    if not email:
        raise TokenError("malformed claims")
    return film_id, email


def decode(token: str) -> dict[str, object]:
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("invalid token") from exc


class Principal:
    """Who is making the request, and which film they are scoped to."""

    __slots__ = ("role", "film_id", "subject")

    def __init__(self, role: Role, film_id: uuid.UUID, subject: uuid.UUID) -> None:
        self.role = role
        self.film_id = film_id
        self.subject = subject

    @property
    def guest_id(self) -> uuid.UUID:
        if self.role != "guest":
            raise TokenError("not a guest token")
        return self.subject

    @property
    def seat_id(self) -> uuid.UUID:
        if self.role not in SEAT_ROLES:
            raise TokenError("not a seat token")
        return self.subject


def parse(token: str) -> Principal:
    claims = decode(token)
    role = claims.get("role")
    if role not in ("guest", "host", "cohost", "photographer"):
        raise TokenError("unknown role")
    try:
        film_id = uuid.UUID(str(claims["film_id"]))
        subject = uuid.UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise TokenError("malformed claims") from exc
    return Principal(role, film_id, subject)
