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
Role = Literal["guest", "host"]

# Long enough to outlive a wedding and the reveal that follows it.
GUEST_TOKEN_TTL = timedelta(days=30)
HOST_TOKEN_TTL = timedelta(days=365)


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


def parse(token: str) -> Principal:
    claims = decode(token)
    role = claims.get("role")
    if role not in ("guest", "host"):
        raise TokenError("unknown role")
    try:
        film_id = uuid.UUID(str(claims["film_id"]))
        subject = uuid.UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise TokenError("malformed claims") from exc
    return Principal(role, film_id, subject)
