"""Co-host and photographer seats.

A wedding is not run by one phone. The couple share the job, a planner needs to
hide a bad shot, and the paid photographer wants the originals without being
able to develop the film early or change the room size.

There are still no accounts, so a seat is a row plus a token that points at it.
Authorisation reads the row on every request, which is the only reason
revocation can be immediate.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import FilmSeat

log = get_logger(__name__)

# One couple, a planner, and a photographer, with room to spare. The cap exists
# so a leaked host token cannot quietly mint a hundred credentials.
MAX_ACTIVE_SEATS = 10


class SeatError(Exception):
    pass


class UnknownSeat(SeatError):
    pass


class SeatRevoked(SeatError):
    pass


class TooManySeats(SeatError):
    pass


async def create_seat(
    session: AsyncSession, *, film_id: uuid.UUID, role: str, label: str
) -> FilmSeat:
    if role not in ("cohost", "photographer"):
        raise SeatError(f"unknown seat role {role}")
    if len(await active_seats(session, film_id)) >= MAX_ACTIVE_SEATS:
        raise TooManySeats(f"a film can have {MAX_ACTIVE_SEATS} active seats")

    seat = FilmSeat(film_id=film_id, role=role, label=label.strip() or role)
    session.add(seat)
    await session.flush()
    log.info("seat.created", film_id=str(film_id), seat_id=str(seat.id), role=role)
    return seat


async def active_seats(session: AsyncSession, film_id: uuid.UUID) -> list[FilmSeat]:
    result = await session.execute(
        select(FilmSeat)
        .where(FilmSeat.film_id == film_id, FilmSeat.revoked_at.is_(None))
        .order_by(FilmSeat.created_at)
    )
    return list(result.scalars().all())


async def load_active(session: AsyncSession, *, film_id: uuid.UUID, seat_id: uuid.UUID) -> FilmSeat:
    """The authorisation read. Raises rather than returning None on purpose."""
    seat = await session.get(FilmSeat, seat_id)
    if seat is None or seat.film_id != film_id:
        raise UnknownSeat("seat does not belong to this film")
    if seat.revoked_at is not None:
        raise SeatRevoked("this access has been removed")
    return seat


async def claim(session: AsyncSession, *, film_id: uuid.UUID, seat_id: uuid.UUID) -> FilmSeat:
    seat = await load_active(session, film_id=film_id, seat_id=seat_id)
    if seat.claimed_at is None:
        seat.claimed_at = datetime.now(UTC)
        await session.flush()
    log.info("seat.claimed", film_id=str(film_id), seat_id=str(seat.id), role=seat.role)
    return seat


async def revoke(session: AsyncSession, *, film_id: uuid.UUID, seat_id: uuid.UUID) -> FilmSeat:
    seat = await session.get(FilmSeat, seat_id)
    if seat is None or seat.film_id != film_id:
        raise UnknownSeat("seat does not belong to this film")
    if seat.revoked_at is None:
        seat.revoked_at = datetime.now(UTC)
        await session.flush()
        log.info("seat.revoked", film_id=str(film_id), seat_id=str(seat.id), role=seat.role)
    return seat
