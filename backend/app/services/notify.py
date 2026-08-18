"""Host emails: magic-link recovery, reveal, and the month-11 storage warning.

Beat runs these on a timer. Reveal also kicks the developed-film pass after a
host taps "develop now", so the morning-after mail is not waiting on the next
tick. Both paths share the same idempotent columns.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import Film
from app.services import mail, tokens
from app.services.catalog import KEEP_FOREVER

log = get_logger(__name__)

RETENTION_WARNING_DAYS = 30


def normalize_email(raw: str) -> str:
    email = raw.strip().lower()
    local, sep, domain = email.partition("@")
    if (
        not sep
        or not local
        or not domain
        or "." not in domain
        or " " in email
        or len(email) > 254
    ):
        raise ValueError("invalid email")
    return email


def host_login_url(code: str, email: str, film_id: uuid.UUID) -> str:
    token = tokens.issue_magic_token(film_id, email)
    base = get_settings().public_web_url.rstrip("/")
    return f"{base}/f/{code}/host?magic={token}"


def send_host_login(film: Film) -> None:
    if not film.host_email:
        return
    url = host_login_url(film.code, film.host_email, film.id)
    mail.send(
        film.host_email,
        f"Your Filmroll host link for {film.title}",
        (
            f"Open this link on any device to manage {film.title}:\n\n"
            f"{url}\n\n"
            "It expires in 30 minutes. Anyone with this email can request a new one."
        ),
    )


def send_developed(film: Film) -> None:
    if not film.host_email:
        return
    base = get_settings().public_web_url.rstrip("/")
    gallery = f"{base}/f/{film.code}/gallery"
    host = host_login_url(film.code, film.host_email, film.id)
    mail.send(
        film.host_email,
        f"{film.title} has developed",
        (
            f"{film.title} is ready to look at.\n\n"
            f"Gallery: {gallery}\n"
            f"Host tools: {host}\n"
        ),
    )


def send_retention_warning(film: Film) -> None:
    if not film.host_email:
        return
    host = host_login_url(film.code, film.host_email, film.id)
    when = film.storage_until.strftime("%d %B %Y")
    mail.send(
        film.host_email,
        f"{film.title} will be removed on {when}",
        (
            f"The photos from {film.title} are kept until {when}. "
            f"The ZIP of originals is always free; paying {KEEP_FOREVER.label.lower()} "
            "keeps the gallery too.\n\n"
            f"Host tools: {host}\n"
        ),
    )


def notify_developed_films(session: Session) -> int:
    """Email hosts whose films have developed and have not been notified yet."""
    developed = or_(Film.revealed_at.isnot(None), Film.reveal_at <= func.now())
    rows = list(
        session.execute(
            select(Film).where(
                Film.deleted_at.is_(None),
                Film.host_email.isnot(None),
                Film.reveal_notified_at.is_(None),
                developed,
            )
        )
        .scalars()
        .all()
    )
    sent = 0
    now = datetime.now(UTC)
    for film in rows:
        send_developed(film)
        film.reveal_notified_at = now
        sent += 1
    if sent:
        log.info("mail.developed_notified", count=sent)
    return sent


def notify_retention_films(session: Session) -> int:
    """Warn hosts 30 days before storage_until, once, unless they paid to keep."""
    now = datetime.now(UTC)
    window_start = now
    window_end = now + timedelta(days=RETENTION_WARNING_DAYS)
    rows = list(
        session.execute(
            select(Film).where(
                Film.deleted_at.is_(None),
                Film.host_email.isnot(None),
                Film.keep_forever.is_(False),
                Film.retention_notified_at.is_(None),
                Film.storage_until > window_start,
                Film.storage_until <= window_end,
            )
        )
        .scalars()
        .all()
    )
    sent = 0
    for film in rows:
        send_retention_warning(film)
        film.retention_notified_at = now
        sent += 1
    if sent:
        log.info("mail.retention_notified", count=sent)
    return sent
