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
from app.core.logging import get_logger
from app.db.models import Film, Guest, Shot, ShotState
from app.services import pins, storage
from app.services.catalog import CLIPS_PER_GUEST, FREE_GUEST_CAP, STORAGE_INCLUDED_DAYS
from app.services.notify import normalize_email

# Ambiguous glyphs removed: no O/0, no I/1, so a code read off a table card or
# an OCR'd QR fallback cannot be mistyped.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6

log = get_logger(__name__)


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


class ClipLimitReached(FilmError):
    pass


class VideoPackRequired(FilmError):
    """Clips are a paid add-on; this film has not bought it."""


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


class RevealLocked(FilmError):
    """The reveal time can no longer be moved.

    Developing is one-way. Once a gallery has been open, pushing the reveal into
    the future would hide photos guests have already seen, so the schedule
    freezes the moment a film develops.
    """


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


async def load_by_code(
    session: AsyncSession, code: str, *, include_deleted: bool = False
) -> FilmView:
    """Deleted films are invisible by default.

    ``include_deleted`` exists for exactly one caller, restore, which has to be
    able to see what everything else is required to pretend is gone.
    """
    conditions = [func.upper(Film.code) == code.upper()]
    if not include_deleted:
        conditions.append(Film.deleted_at.is_(None))
    row = (
        await session.execute(select(Film, _IS_DEVELOPED, _IS_CLOSED).where(*conditions))
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
    reveal_at: datetime | None,
    shot_limit: int,
    guest_cap: int,
    host_email: str | None = None,
    instant_reveal: bool = False,
    shared_gallery: bool = True,
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

    # A live film develops the moment it exists. Stamp revealed_at as well as
    # reveal_at: Python now() can sit a millisecond ahead of Postgres now(),
    # and `now() >= reveal_at` would then be false on the create response.
    if instant_reveal:
        now = datetime.now(UTC)
        reveal_at = now
        revealed_at: datetime | None = now
    elif reveal_at is None:
        raise FilmError("a scheduled film needs a reveal time")
    else:
        revealed_at = None

    entitled = FREE_GUEST_CAP
    film = Film(
        code=code,
        title=title,
        event_type=event_type,
        closes_at=closes_at,
        reveal_at=reveal_at,
        revealed_at=revealed_at,
        instant_reveal=instant_reveal,
        shared_gallery=shared_gallery,
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


_RESERVE_PHOTO_SQL = text(
    """
    INSERT INTO shots (id, film_id, guest_id, state, storage_key, content_type, kind, reserved_at)
    SELECT :shot_id, :film_id, :guest_id, 'reserved', :storage_key, :content_type, 'photo', now()
    WHERE (
        SELECT unlimited_shots FROM films WHERE id = :film_id
    ) OR (
        SELECT count(*) FROM shots
        WHERE guest_id = :guest_id AND state <> 'expired' AND kind = 'photo'
    ) < (SELECT shot_limit FROM films WHERE id = :film_id)
    ON CONFLICT (id) DO NOTHING
    RETURNING id
    """
)

# The pack is re-read here rather than trusted from the loaded film, for the
# same reason the photo cap is: this statement is the only thing that decides.
_RESERVE_CLIP_SQL = text(
    """
    INSERT INTO shots (id, film_id, guest_id, state, storage_key, content_type, kind, reserved_at)
    SELECT :shot_id, :film_id, :guest_id, 'reserved', :storage_key, :content_type, 'clip', now()
    WHERE (
        SELECT video_pack FROM films WHERE id = :film_id
    ) AND (
        SELECT count(*) FROM shots
        WHERE guest_id = :guest_id AND state <> 'expired' AND kind = 'clip'
    ) < :clip_limit
    ON CONFLICT (id) DO NOTHING
    RETURNING id
    """
)

_CLIP_EXTENSIONS = {"video/mp4": "mp4", "video/quicktime": "mov", "video/webm": "webm"}


async def reserve_shot(
    session: AsyncSession,
    *,
    film: Film,
    guest_id: uuid.UUID,
    shot_id: uuid.UUID,
    content_type: str = "image/jpeg",
    kind: str = "photo",
) -> tuple[str, bool]:
    """Claim a slot in the roll. Returns (storage_key, was_already_reserved).

    The shot id comes from the client, which is what makes the whole upload
    idempotent: a phone on venue wifi will retry, and every retry collapses onto
    the same row and the same object.
    """
    if kind == "clip":
        if not film.video_pack:
            raise VideoPackRequired(film.code)
        content_type = content_type.split(";")[0].strip().lower()
        if content_type not in get_settings().allowed_clip_type_set:
            raise UploadTypeRejected(content_type)

    # Serialise reservations for this guest. See join_film for why counting
    # alone is not enough under READ COMMITTED.
    await session.execute(select(Guest.id).where(Guest.id == guest_id).with_for_update())

    params: dict[str, object] = {
        "shot_id": shot_id,
        "film_id": film.id,
        "guest_id": guest_id,
        "content_type": content_type,
    }
    if kind == "clip":
        key = storage.original_key(str(film.id), str(shot_id), _CLIP_EXTENSIONS[content_type])
        params |= {"storage_key": key, "clip_limit": CLIPS_PER_GUEST}
        inserted = await session.scalar(_RESERVE_CLIP_SQL, params)
    else:
        key = storage.original_key(str(film.id), str(shot_id))
        params["storage_key"] = key
        inserted = await session.scalar(_RESERVE_PHOTO_SQL, params)
    if inserted is not None:
        return key, False

    # No row inserted means either a replay of a shot id we already hold, or a
    # genuine cap rejection. Distinguish so retries do not look like failures.
    existing = await session.scalar(
        select(Shot).where(Shot.id == shot_id, Shot.guest_id == guest_id)
    )
    if existing is not None:
        return existing.storage_key, True

    if kind == "clip":
        raise ClipLimitReached(str(guest_id))
    raise ShotLimitReached(str(guest_id))


async def shot_content_type(session: AsyncSession, shot_id: uuid.UUID) -> str:
    return (await session.scalar(select(Shot.content_type).where(Shot.id == shot_id))) or (
        "image/jpeg"
    )


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
    is_clip = shot.kind == "clip"
    max_bytes = settings.max_clip_bytes if is_clip else settings.max_upload_bytes
    allowed = settings.allowed_clip_type_set if is_clip else settings.allowed_upload_type_set
    if info.size > max_bytes:
        await storage.delete_object(shot.storage_key)
        await _release_reservation(session, shot_id)
        raise UploadTooLarge(f"{info.size} bytes exceeds {max_bytes}")

    if (info.content_type or "").split(";")[0].strip().lower() not in allowed:
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


async def set_join_pin(session: AsyncSession, film: Film, pin: str | None) -> None:
    """``None`` removes the gate. Guests already inside are unaffected either
    way: their token is what proves they joined, not the PIN."""
    film.join_pin_hash = None if pin is None else pins.hash_pin(pin)
    await session.flush()
    log.info("film.pin_set", film_id=str(film.id), enabled=pin is not None)


class FilmAlreadyPurged(Exception):
    """The grace period lapsed and the photos are gone. Nothing to restore."""


def purge_deadline(deleted_at: datetime) -> datetime:
    return deleted_at + timedelta(days=get_settings().deleted_film_grace_days)


async def soft_delete(session: AsyncSession, film: Film) -> datetime:
    """Take the film away now, destroy the photos later.

    Guests and the gallery 404 from this moment, which is what a host asking to
    delete an event actually wants. The bytes survive the grace window because
    these are usually the only copies of the photographs in existence, and an
    accidental tap should not be the end of them.

    Returns the moment the objects become unrecoverable.
    """
    if film.deleted_at is None:
        film.deleted_at = datetime.now(UTC)
        await session.flush()
        log.info("film.deleted", film_id=str(film.id), code=film.code)
    return purge_deadline(film.deleted_at)


async def restore(session: AsyncSession, film: Film) -> None:
    if film.purged_at is not None:
        raise FilmAlreadyPurged(film.code)
    if film.deleted_at is not None:
        film.deleted_at = None
        await session.flush()
        log.info("film.restored", film_id=str(film.id), code=film.code)


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
    shared_gallery: bool | None = None,
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
            .where(Shot.film_id == film.id, Shot.state != ShotState.EXPIRED, Shot.kind == "photo")
            .group_by(Shot.guest_id)
            .order_by(func.count().desc())
            .limit(1)
        )
        if shot_limit < (fullest or 0):
            raise LimitBelowUse(f"{shot_limit} is below a guest's {fullest} shots")
        film.shot_limit = shot_limit

    if closes_at is not None:
        film.closes_at = closes_at

    # Re-sending the current value is how the dashboard saves a form, so only a
    # real change is judged.
    if reveal_at is not None and reveal_at != film.reveal_at:
        now = datetime.now(UTC)
        if film.instant_reveal:
            raise RevealLocked("a live film has no reveal time to set")
        if (film.revealed_at is not None or film.reveal_at <= now) and reveal_at > now:
            raise RevealLocked("this film has already developed; its photos are out")
        film.reveal_at = reveal_at
    if host_email is not None:
        film.host_email = _optional_email(host_email) if host_email else None
    if shared_gallery is not None:
        film.shared_gallery = shared_gallery

    await session.flush()
    await session.refresh(film)
    return film


# --------------------------------------------------------------------- queries


# A clip's original is whatever the phone recorded: any length, any codec, with
# its GPS track still in the metadata. Only the transcode is ever served, so a
# clip is not a shot at all until the worker has produced it.
_IS_PLAYABLE = (Shot.kind == "photo") | Shot.derivative_at.isnot(None)


async def visible_shots(
    session: AsyncSession, film_id: uuid.UUID, *, guest_id: uuid.UUID | None = None
) -> list[Shot]:
    """Shots eligible to be shown, exported or fed into a recap.

    Hidden and still-reserved shots are excluded here, in one place, so no
    caller can accidentally leak them. ``guest_id`` narrows to one guest's
    roll, which is how a private gallery is enforced without a second query.
    """
    conditions = [
        Shot.film_id == film_id,
        Shot.state == ShotState.UPLOADED,
        Shot.hidden_at.is_(None),
        _IS_PLAYABLE,
    ]
    if guest_id is not None:
        conditions.append(Shot.guest_id == guest_id)
    result = await session.execute(
        select(Shot)
        .where(*conditions)
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
        .where(Shot.film_id == film_id, Shot.state == ShotState.UPLOADED, _IS_PLAYABLE)
        .options(selectinload(Shot.guest))
        .order_by(Shot.uploaded_at)
    )
    return list(result.scalars().all())


async def shots_remaining(session: AsyncSession, *, film: Film, guest_id: uuid.UUID) -> int:
    if film.unlimited_shots:
        return 10_000
    used = await _count_live(session, guest_id=guest_id, kind="photo")
    return max(film.shot_limit - used, 0)


async def clips_remaining(session: AsyncSession, *, film: Film, guest_id: uuid.UUID) -> int:
    if not film.video_pack:
        return 0
    used = await _count_live(session, guest_id=guest_id, kind="clip")
    return max(CLIPS_PER_GUEST - used, 0)


async def _count_live(session: AsyncSession, *, guest_id: uuid.UUID, kind: str) -> int:
    used = await session.scalar(
        select(func.count())
        .select_from(Shot)
        .where(Shot.guest_id == guest_id, Shot.state != ShotState.EXPIRED, Shot.kind == kind)
    )
    return used or 0


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
