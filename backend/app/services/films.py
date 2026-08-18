"""Film, guest and shot operations.

The caps enforced here are the product's pricing tiers, so every one of them is
a correctness boundary rather than a convenience check.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.models import Film, Guest, Shot, ShotState
from app.services import storage

# Ambiguous glyphs removed: no O/0, no I/1, so a code read off a table card or
# an OCR'd QR fallback cannot be mistyped.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6


class FilmError(Exception):
    """Base class for expected, client-visible failures."""


class FilmNotFound(FilmError):
    pass


class FilmClosed(FilmError):
    pass


class GuestCapReached(FilmError):
    pass


class ShotLimitReached(FilmError):
    pass


class ShotNotFound(FilmError):
    pass


class UploadMissing(FilmError):
    pass


def generate_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


# --------------------------------------------------------------------- reading

# Reveal is derived, never stored as a flag flipped by a scheduler. If a cron
# owned this boolean, one dead worker would mean a gallery that silently never
# opens. Evaluating it in SQL also means the database clock decides, so the
# answer does not drift between API replicas.
_IS_DEVELOPED = Film.revealed_at.isnot(None) | (func.now() >= Film.reveal_at)
_IS_CLOSED = func.now() >= Film.closes_at


class FilmView:
    """A film plus the time-dependent state computed by the database."""

    __slots__ = ("film", "is_developed", "is_closed")

    def __init__(self, film: Film, is_developed: bool, is_closed: bool) -> None:
        self.film = film
        self.is_developed = is_developed
        self.is_closed = is_closed


async def load_by_code(session: AsyncSession, code: str) -> FilmView:
    row = (
        await session.execute(
            select(Film, _IS_DEVELOPED, _IS_CLOSED).where(
                func.upper(Film.code) == code.upper(), Film.deleted_at.is_(None)
            )
        )
    ).first()
    if row is None:
        raise FilmNotFound(code)
    film, is_developed, is_closed = row
    return FilmView(film, bool(is_developed), bool(is_closed))


async def load_by_id(session: AsyncSession, film_id: uuid.UUID) -> FilmView:
    row = (
        await session.execute(
            select(Film, _IS_DEVELOPED, _IS_CLOSED).where(
                Film.id == film_id, Film.deleted_at.is_(None)
            )
        )
    ).first()
    if row is None:
        raise FilmNotFound(str(film_id))
    film, is_developed, is_closed = row
    return FilmView(film, bool(is_developed), bool(is_closed))


# --------------------------------------------------------------------- writing


async def create_film(
    session: AsyncSession,
    *,
    title: str,
    event_type: str,
    closes_at: datetime,
    reveal_at: datetime,
    shot_limit: int,
    guest_cap: int,
) -> Film:
    # Codes are short enough that collisions are possible; retry rather than
    # surfacing a unique-violation to the host.
    for _ in range(10):
        code = generate_code()
        exists = await session.scalar(select(Film.id).where(Film.code == code))
        if exists is None:
            break
    else:  # pragma: no cover - astronomically unlikely
        raise FilmError("could not allocate a unique film code")

    film = Film(
        code=code,
        title=title,
        event_type=event_type,
        closes_at=closes_at,
        reveal_at=reveal_at,
        shot_limit=shot_limit,
        guest_cap=guest_cap,
    )
    session.add(film)
    await session.flush()
    return film


async def join_film(session: AsyncSession, film: Film, display_name: str) -> Guest:
    """Add a guest, enforcing the guest cap under concurrency.

    The film row is locked first. Counting guests in a subquery takes no lock,
    so without this two simultaneous joins at the boundary would both observe
    cap-1 and both succeed.
    """
    await session.execute(select(Film.id).where(Film.id == film.id).with_for_update())

    current = await session.scalar(
        select(func.count()).select_from(Guest).where(Guest.film_id == film.id)
    )
    if (current or 0) >= film.guest_cap:
        raise GuestCapReached(film.code)

    guest = Guest(film_id=film.id, display_name=display_name)
    session.add(guest)
    await session.flush()
    return guest


_RESERVE_SQL = text(
    """
    INSERT INTO shots (id, film_id, guest_id, state, storage_key, content_type, reserved_at)
    SELECT :shot_id, :film_id, :guest_id, 'reserved', :storage_key, :content_type, now()
    WHERE (
        SELECT count(*) FROM shots
        WHERE guest_id = :guest_id AND state <> 'expired'
    ) < (SELECT shot_limit FROM films WHERE id = :film_id)
    ON CONFLICT (id) DO NOTHING
    RETURNING id
    """
)


async def reserve_shot(
    session: AsyncSession,
    *,
    film: Film,
    guest_id: uuid.UUID,
    shot_id: uuid.UUID,
    content_type: str = "image/jpeg",
) -> tuple[str, bool]:
    """Claim a slot in the roll. Returns (storage_key, was_already_reserved).

    The shot id comes from the client, which is what makes the whole upload
    idempotent: a phone on venue wifi will retry, and every retry collapses onto
    the same row and the same object.
    """
    # Serialise reservations for this guest. See join_film for why counting
    # alone is not enough under READ COMMITTED.
    await session.execute(select(Guest.id).where(Guest.id == guest_id).with_for_update())

    key = storage.original_key(str(film.id), str(shot_id))
    inserted = await session.scalar(
        _RESERVE_SQL,
        {
            "shot_id": shot_id,
            "film_id": film.id,
            "guest_id": guest_id,
            "storage_key": key,
            "content_type": content_type,
        },
    )
    if inserted is not None:
        return key, False

    # No row inserted means either a replay of a shot id we already hold, or a
    # genuine cap rejection. Distinguish so retries do not look like failures.
    existing = await session.scalar(
        select(Shot).where(Shot.id == shot_id, Shot.guest_id == guest_id)
    )
    if existing is not None:
        return existing.storage_key, True

    raise ShotLimitReached(str(guest_id))


async def commit_shot(
    session: AsyncSession, *, film: Film, guest_id: uuid.UUID, shot_id: uuid.UUID
) -> Shot:
    """Mark an uploaded shot as live once its bytes are confirmed present."""
    shot = await session.scalar(
        select(Shot).where(
            Shot.id == shot_id, Shot.guest_id == guest_id, Shot.film_id == film.id
        )
    )
    if shot is None:
        raise ShotNotFound(str(shot_id))

    if shot.state is ShotState.UPLOADED:
        return shot  # idempotent replay

    # Trusting the client here would let a guest burn a slot with no photo, or
    # worse, put a row in the gallery that renders as a broken image.
    if not await storage.object_exists(shot.storage_key):
        raise UploadMissing(str(shot_id))

    # Timestamp comes from the database clock, not the API process, so ordering
    # stays consistent across replicas.
    await session.execute(
        update(Shot)
        .where(Shot.id == shot_id)
        .values(state=ShotState.UPLOADED, uploaded_at=func.now())
    )
    await session.flush()
    await session.refresh(shot)
    return shot


async def reveal_now(session: AsyncSession, film: Film) -> None:
    """Host override. Idempotent: revealing twice keeps the first timestamp."""
    await session.execute(
        update(Film)
        .where(Film.id == film.id, Film.revealed_at.is_(None))
        .values(revealed_at=func.now())
    )


async def hide_shot(session: AsyncSession, *, film: Film, shot_id: uuid.UUID) -> None:
    await session.execute(
        update(Shot)
        .where(Shot.id == shot_id, Shot.film_id == film.id, Shot.hidden_at.is_(None))
        .values(hidden_at=func.now())
    )


# --------------------------------------------------------------------- queries


async def visible_shots(session: AsyncSession, film_id: uuid.UUID) -> list[Shot]:
    """Shots eligible to be shown, exported or fed into a recap.

    Hidden and still-reserved shots are excluded here, in one place, so no
    caller can accidentally leak them.
    """
    result = await session.execute(
        select(Shot)
        .where(
            Shot.film_id == film_id,
            Shot.state == ShotState.UPLOADED,
            Shot.hidden_at.is_(None),
        )
        # Eager-loaded because the gallery renders attribution. A lazy load
        # would raise MissingGreenlet under the async session.
        .options(selectinload(Shot.guest))
        .order_by(Shot.uploaded_at)
    )
    return list(result.scalars().all())


async def shots_remaining(
    session: AsyncSession, *, film: Film, guest_id: uuid.UUID
) -> int:
    used = await session.scalar(
        select(func.count())
        .select_from(Shot)
        .where(Shot.guest_id == guest_id, Shot.state != ShotState.EXPIRED)
    )
    return max(film.shot_limit - (used or 0), 0)


async def guest_count(session: AsyncSession, film_id: uuid.UUID) -> int:
    return (
        await session.scalar(
            select(func.count()).select_from(Guest).where(Guest.film_id == film_id)
        )
    ) or 0


async def expire_abandoned_reservations(session: AsyncSession) -> list[Shot]:
    """Reclaim slots whose upload never arrived.

    Reserved shots deliberately count against the cap while they are alive,
    otherwise a guest could bypass the limit by abandoning reservations. This
    is what gives those slots back.
    """
    cutoff = timedelta(minutes=get_settings().reservation_ttl_minutes)
    result = await session.execute(
        update(Shot)
        .where(
            Shot.state == ShotState.RESERVED,
            Shot.reserved_at < func.now() - cutoff,
        )
        .values(state=ShotState.EXPIRED)
        .returning(Shot)
    )
    return list(result.scalars().all())
