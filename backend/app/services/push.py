"""Expo push tokens for guests waiting on a film to develop.

The host already gets email. Guests are holding a camera, so a notification on
that phone is the matching channel. Tokens are stored against the guest row,
not an account: there are still no accounts.

An empty ``EXPO_PUSH_URL`` records messages in ``outbox`` instead of opening a
socket, matching how tests capture mail.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import GuestPushToken

log = get_logger(__name__)

# Expo's own token shape. Anything else would be a URL we might accidentally
# POST to, so this is a safety check as much as a format check.
_TOKEN = re.compile(r"^Expo(nent)?PushToken\[[A-Za-z0-9_-]+\]$")
LOCALES = frozenset({"en", "es", "fr"})

_COPY = {
    "en": ("{title} has developed", "Open the gallery to see the photos."),
    "es": ("{title} se ha revelado", "Abre la galería para ver las fotos."),
    "fr": ("{title} a été révélé", "Ouvrez la galerie pour voir les photos."),
}


class PushError(Exception):
    pass


class InvalidToken(PushError):
    pass


class InvalidLocale(PushError):
    pass


@dataclass(frozen=True, slots=True)
class Outgoing:
    to: str
    title: str
    body: str
    code: str


outbox: list[Outgoing] = []


def validate_token(raw: str) -> str:
    token = raw.strip()
    if not _TOKEN.fullmatch(token):
        raise InvalidToken("not an Expo push token")
    return token


def validate_locale(raw: str) -> str:
    locale = raw.strip().lower()
    if locale not in LOCALES:
        raise InvalidLocale(locale)
    return locale


async def upsert_token(
    session: AsyncSession,
    *,
    guest_id: uuid.UUID,
    film_id: uuid.UUID,
    token: str,
    locale: str = "en",
) -> None:
    """Remember where to ping this guest. A new phone overwrites the old one."""
    token = validate_token(token)
    locale = validate_locale(locale)
    now = datetime.now(UTC)
    await session.execute(
        pg_insert(GuestPushToken)
        .values(
            guest_id=guest_id,
            film_id=film_id,
            token=token,
            locale=locale,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=[GuestPushToken.guest_id],
            set_={"token": token, "locale": locale, "film_id": film_id, "updated_at": now},
        )
    )


def tokens_for_film(session: Session, film_id: uuid.UUID) -> list[GuestPushToken]:
    return list(
        session.execute(select(GuestPushToken).where(GuestPushToken.film_id == film_id))
        .scalars()
        .all()
    )


def send_developed(film_title: str, film_code: str, rows: list[GuestPushToken]) -> int:
    """Best-effort fan-out. Failures must not roll back the host email."""
    if not rows:
        return 0
    messages = [_message(film_title, film_code, row) for row in rows]
    settings = get_settings()
    if not settings.expo_push_url:
        outbox.extend(messages)
        log.info("push.captured", count=len(messages), code=film_code)
        return len(messages)
    try:
        _deliver(settings.expo_push_url, messages)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        log.warning("push.deliver_failed", code=film_code, error=str(exc))
        return 0
    log.info("push.sent", count=len(messages), code=film_code)
    return len(messages)


def _message(title: str, code: str, row: GuestPushToken) -> Outgoing:
    headline, body = _COPY.get(row.locale, _COPY["en"])
    return Outgoing(
        to=row.token,
        title=headline.format(title=title),
        body=body,
        code=code,
    )


def _deliver(url: str, messages: list[Outgoing]) -> None:
    payload = [
        {
            "to": item.to,
            "title": item.title,
            "body": item.body,
            "sound": "default",
            "data": {"code": item.code, "url": f"filmroll://f/{item.code}"},
        }
        for item in messages
    ]
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()
