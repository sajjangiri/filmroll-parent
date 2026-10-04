"""Guests flagging a photo for the host.

The host cannot watch a hundred phones, but the hundred phones can watch each
other. This is the channel for that, and it deliberately stops at telling the
host: see ``ShotReport`` for why a report never hides anything by itself.
"""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Shot, ShotReport

log = get_logger(__name__)

Reason = Literal["inappropriate", "private", "other"]
REASONS: frozenset[str] = frozenset({"inappropriate", "private", "other"})


class ReportError(Exception):
    pass


class UnknownShot(ReportError):
    pass


class InvalidReason(ReportError):
    pass


async def report_shot(
    session: AsyncSession,
    *,
    film_id: uuid.UUID,
    shot_id: uuid.UUID,
    guest_id: uuid.UUID,
    reason: str,
) -> int:
    """Record one guest's report. Returns the shot's total report count.

    Idempotent by ``(shot_id, guest_id)``: a guest tapping twice, or a retry on
    a flaky connection at a venue, must not inflate the number the host sees.
    """
    if reason not in REASONS:
        raise InvalidReason(reason)

    shot = await session.get(Shot, shot_id)
    if shot is None or shot.film_id != film_id:
        raise UnknownShot(str(shot_id))

    await session.execute(
        pg_insert(ShotReport)
        .values(id=uuid.uuid4(), shot_id=shot_id, guest_id=guest_id, reason=reason)
        # A second report from the same guest keeps the original reason. The
        # first thing they reached for is the more honest signal.
        .on_conflict_do_nothing(constraint="uq_shot_reports_shot_guest")
    )
    await session.flush()

    total = await count_for_shot(session, shot_id)
    log.info(
        "shot.reported",
        film_id=str(film_id),
        shot_id=str(shot_id),
        reason=reason,
        total=total,
    )
    return total


async def count_for_shot(session: AsyncSession, shot_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count()).select_from(ShotReport).where(ShotReport.shot_id == shot_id)
    )
    return int(result.scalar_one())


async def counts_for_film(session: AsyncSession, film_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """Report totals keyed by shot id, for the host inbox.

    One grouped query rather than a count per photo, because the inbox renders
    every shot in the film.
    """
    result = await session.execute(
        select(ShotReport.shot_id, func.count())
        .join(Shot, Shot.id == ShotReport.shot_id)
        .where(Shot.film_id == film_id)
        .group_by(ShotReport.shot_id)
    )
    return {row[0]: int(row[1]) for row in result.all()}


async def reported_by_guest(
    session: AsyncSession, *, film_id: uuid.UUID, guest_id: uuid.UUID
) -> set[uuid.UUID]:
    """Shots this guest already flagged, so the UI can say so."""
    result = await session.execute(
        select(ShotReport.shot_id)
        .join(Shot, Shot.id == ShotReport.shot_id)
        .where(Shot.film_id == film_id, ShotReport.guest_id == guest_id)
    )
    return {row[0] for row in result.all()}
