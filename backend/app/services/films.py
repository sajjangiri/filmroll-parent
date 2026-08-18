"""Film, guest and shot operations.

The caps enforced here are the product's pricing tiers, so every one of them is
a correctness boundary rather than a convenience check.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.models import Film, Guest, Shot, ShotState
from app.services import storage
from app.services.catalog import FREE_GUEST_CAP, STORAGE_INCLUDED_DAYS
from app.services.notify import normalize_email

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


class UploadTooLarge(FilmError):
    pass


class UploadTypeRejected(FilmError):
    pass


class ShotExpired(FilmError):
    pass


class CapBelowHeadcount(FilmError):
    pass


class LimitBelowUse(FilmError):
    pass


class ShotNotOwned(FilmError):
    pass


class CapAboveEntitlement(FilmError):
    pass


class InvalidEmail(FilmError):
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
    host_email: str | None = None,
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

    entitled = FREE_GUEST_CAP
    film = Film(
        code=code,
        title=title,
        event_type=event_type,
        closes_at=closes_at,
        reveal_at=reveal_at,
        shot_limit=shot_limit,
        guest_cap=min(guest_cap, entitled),
        entitled_guest_cap=entitled,
        keep_forever=False,
        unlimited_shots=False,
        storage_until=datetime.now(UTC) + timedelta(days=STORAGE_INCLUDED_DAYS),
        host_email=_optional_email(host_email),
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
        SELECT unlimited_shots FROM films WHERE id = :film_id
    ) OR (
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
        select(Shot).where(Shot.id == shot_id, Shot.guest_id == guest_id, Shot.film_id == film.id)
    )
    if shot is None:
        raise ShotNotFound(str(shot_id))

    if shot.state is ShotState.UPLOADED:
        return shot  # idempotent replay

    # An expired slot has already been handed back, so the cap no longer counts
    # it. Committing it now would put the photo in the gallery *and* leave the
    # replacement slot outstanding, letting a guest shoot past the limit one
    # rejected upload at a time. The id is spent; a retry must reserve a new one.
    if shot.state is ShotState.EXPIRED:
        raise ShotExpired(str(shot_id))

    # Trusting the client here would let a guest burn a slot with no photo, or
    # worse, put a row in the gallery that renders as a broken image.
    info = await storage.stat_object(shot.storage_key)
    if info is None:
        raise UploadMissing(str(shot_id))

    # A presigned PUT bounds neither the size nor the real content of the body,
    # so the only honest place to check is here, once the bytes exist. Rejected
    # uploads are deleted rather than left to the sweeper: storage is billed by
    # the byte, and the slot is handed straight back.
    settings = get_settings()
    if info.size > settings.max_upload_bytes:
        await storage.delete_object(shot.storage_key)
        await _release_reservation(session, shot_id)
        raise UploadTooLarge(f"{info.size} bytes exceeds {settings.max_upload_bytes}")

    if info.content_type not in settings.allowed_upload_type_set:
        await storage.delete_object(shot.storage_key)
        await _release_reservation(session, shot_id)
        raise UploadTypeRejected(info.content_type or "unknown")

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


async def _release_reservation(session: AsyncSession, shot_id: uuid.UUID) -> None:
    """Hand a slot back after a rejected upload.

    Marked EXPIRED rather than deleted so the row remains a record that the
    attempt happened, and so commit_shot can refuse to resurrect the id.

    Committed here rather than left to the request. Every caller raises straight
    afterwards, and the session dependency rolls back on exception, so a plain
    flush would be undone and the guest would silently lose a shot. Nothing else
    has been written on this path, so there is no unrelated work to carry along.
    """
    await session.execute(update(Shot).where(Shot.id == shot_id).values(state=ShotState.EXPIRED))
    await session.commit()


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


async def unhide_shot(session: AsyncSession, *, film: Film, shot_id: uuid.UUID) -> None:
    await session.execute(
        update(Shot)
        .where(Shot.id == shot_id, Shot.film_id == film.id, Shot.hidden_at.isnot(None))
        .values(hidden_at=None)
    )


async def retract_shot(
    session: AsyncSession, *, film: Film, guest_id: uuid.UUID, shot_id: uuid.UUID
) -> None:
    """A guest removing their own photo. Same outcome as a host hide."""
    shot = await session.scalar(
        select(Shot).where(Shot.id == shot_id, Shot.film_id == film.id, Shot.guest_id == guest_id)
    )
    if shot is None:
        raise ShotNotOwned(str(shot_id))
    if shot.hidden_at is None:
        await session.execute(update(Shot).where(Shot.id == shot_id).values(hidden_at=func.now()))


async def update_film(
    session: AsyncSession,
    film: Film,
    *,
    closes_at: datetime | None = None,
    reveal_at: datetime | None = None,
    shot_limit: int | None = None,
    guest_cap: int | None = None,
    host_email: str | None = None,
) -> Film:
    if guest_cap is not None:
        current = await guest_count(session, film.id)
        if guest_cap < current:
            raise CapBelowHeadcount(f"{guest_cap} is below {current} guests")
        if guest_cap > film.entitled_guest_cap:
            raise CapAboveEntitlement(
                f"entitled to {film.entitled_guest_cap} guests; pay to raise the cap"
            )
        film.guest_cap = guest_cap

    if shot_limit is not None:
        fullest = await session.scalar(
            select(func.count())
            .select_from(Shot)
            .where(Shot.film_id == film.id, Shot.state != ShotState.EXPIRED)
            .group_by(Shot.guest_id)
            .order_by(func.count().desc())
            .limit(1)
        )
        if shot_limit < (fullest or 0):
            raise LimitBelowUse(f"{shot_limit} is below a guest's {fullest} shots")
        film.shot_limit = shot_limit

    if closes_at is not None:
        film.closes_at = closes_at
    if reveal_at is not None:
        film.reveal_at = reveal_at
    if host_email is not None:
        film.host_email = _optional_email(host_email) if host_email else None

    await session.flush()
    await session.refresh(film)
    return film


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


async def review_shots(session: AsyncSession, film_id: uuid.UUID) -> list[Shot]:
    """Every uploaded shot, including hidden ones. Host review only.

    The gallery uses visible_shots. This is the one query that is allowed to
    see a hidden photo, because the host cannot moderate what they cannot see.
    """
    result = await session.execute(
        select(Shot)
        .where(Shot.film_id == film_id, Shot.state == ShotState.UPLOADED)
        .options(selectinload(Shot.guest))
        .order_by(Shot.uploaded_at)
    )
    return list(result.scalars().all())


async def shots_remaining(session: AsyncSession, *, film: Film, guest_id: uuid.UUID) -> int:
    if film.unlimited_shots:
        return 10_000
    used = await session.scalar(
        select(func.count())
        .select_from(Shot)
        .where(Shot.guest_id == guest_id, Shot.state != ShotState.EXPIRED)
    )
    return max(film.shot_limit - (used or 0), 0)


def _optional_email(raw: str | None) -> str | None:
    if raw is None or not raw.strip():
        return None
    try:
        return normalize_email(raw)
    except ValueError as exc:
        raise InvalidEmail(str(exc)) from exc


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
