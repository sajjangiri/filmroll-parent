"""Background tasks.

Every task here is idempotent. Combined with ``task_acks_late``, that is what
makes at-least-once delivery safe: a worker can die mid-job and the redelivered
message produces the same result rather than a duplicate.
"""

from __future__ import annotations

import io
import uuid
from datetime import timedelta

from PIL import Image
from sqlalchemy import func, select, update

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import Shot, ShotState
from app.db.sync_session import session_scope
from app.services import storage
from app.worker.celery_app import celery_app

log = get_logger(__name__)

THUMBNAIL_MAX = (1280, 1280)
THUMBNAIL_QUALITY = 82


@celery_app.task(name="app.worker.tasks.ping")
def ping() -> str:
    return "pong"


@celery_app.task(
    name="app.worker.tasks.generate_derivatives",
    bind=True,
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def generate_derivatives(self, shot_id: str) -> str:  # type: ignore[no-untyped-def]
    """Build the display-sized image for one shot.

    Originals are never modified. The gallery renders the derivative while the
    untouched original stays available for full-quality download, which is what
    lets a look be changed later without re-uploading anything.
    """
    shot_uuid = uuid.UUID(shot_id)

    with session_scope() as session:
        shot = session.get(Shot, shot_uuid)
        if shot is None:
            log.warning("derivatives.shot_missing", shot_id=shot_id)
            return "missing"
        if shot.derivative_at is not None:
            return "already-done"
        if shot.state is not ShotState.UPLOADED:
            return "not-uploaded"
        original = shot.storage_key
        film_id = str(shot.film_id)

    raw = storage.download_bytes(original)

    buffer = io.BytesIO()
    with Image.open(io.BytesIO(raw)) as source:
        # EXIF is dropped by re-encoding, which removes GPS coordinates and
        # device identifiers before anything is shared with other guests.
        rendered = source.convert("RGB")
        rendered.thumbnail(THUMBNAIL_MAX)
        rendered.save(buffer, format="WEBP", quality=THUMBNAIL_QUALITY, method=4)

    # Deterministic key, so a rerun overwrites in place instead of duplicating.
    storage.upload_bytes(
        storage.derivative_key(film_id, shot_id, "display"),
        buffer.getvalue(),
        "image/webp",
    )

    with session_scope() as session:
        session.execute(
            update(Shot)
            .where(Shot.id == shot_uuid, Shot.derivative_at.is_(None))
            .values(derivative_at=func.now())
        )

    log.info("derivatives.done", shot_id=shot_id, bytes=len(buffer.getvalue()))
    return "ok"


@celery_app.task(name="app.worker.tasks.sweep_abandoned_reservations")
def sweep_abandoned_reservations() -> int:
    """Reclaim slots whose upload never arrived, and bin the orphaned bytes.

    Reserved shots count against the cap while alive, otherwise a guest could
    hold slots open indefinitely to dodge the limit. This hands them back.

    Note this is a cleanup job, not a correctness dependency: if it stops
    running, slots are returned late but nothing breaks and no film is affected.
    """
    ttl = timedelta(minutes=get_settings().reservation_ttl_minutes)

    with session_scope() as session:
        rows = session.execute(
            update(Shot)
            .where(Shot.state == ShotState.RESERVED, Shot.reserved_at < func.now() - ttl)
            .values(state=ShotState.EXPIRED)
            .returning(Shot.id, Shot.storage_key)
        ).all()

    orphans = 0
    for _shot_id, key in rows:
        # An upload that landed without a commit leaves bytes nothing points at.
        if storage.object_exists_sync(key):
            storage.delete_object_sync(key)
            orphans += 1

    if rows:
        log.info("sweeper.expired", reservations=len(rows), orphans_deleted=orphans)
    return len(rows)


@celery_app.task(name="app.worker.tasks.purge_film_objects")
def purge_film_objects(film_id: str) -> int:
    """Remove every object belonging to a deleted film."""
    removed = 0

    def _run() -> int:
        import asyncio

        return asyncio.run(storage.delete_prefix(storage.film_prefix(film_id)))

    removed = _run()
    log.info("film.objects_purged", film_id=film_id, objects=removed)
    return removed


@celery_app.task(name="app.worker.tasks.build_recap_video", bind=True)
def build_recap_video(self, film_id: str) -> None:  # type: ignore[no-untyped-def]
    raise NotImplementedError("Phase 6")


@celery_app.task(name="app.worker.tasks.build_export_archive", bind=True)
def build_export_archive(self, film_id: str) -> None:  # type: ignore[no-untyped-def]
    raise NotImplementedError("Phase 6")


def pending_derivative_ids(limit: int = 100) -> list[str]:
    """Shots that are live but have no derivative yet, for backfills."""
    with session_scope() as session:
        rows = session.execute(
            select(Shot.id)
            .where(Shot.state == ShotState.UPLOADED, Shot.derivative_at.is_(None))
            .limit(limit)
        ).all()
    return [str(row[0]) for row in rows]
