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
from sqlalchemy import delete, func, select, update

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
        if shot.kind != "photo":
            return "not-a-photo"
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
        storage.display_key(film_id, shot_id),
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


@celery_app.task(
    name="app.worker.tasks.transcode_clip",
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
)
def transcode_clip(self, shot_id: str) -> str:  # type: ignore[no-untyped-def]
    """Turn a guest's recording into the one clip anyone will ever see.

    Phones hand over HEVC, VP9 or whatever else they record, at any length, with
    a GPS track in the container metadata. The output is H.264/AAC MP4 (plays
    everywhere, including inside the export ZIP), trimmed to the clip limit,
    at most 720p on the short side, with all metadata dropped. A poster frame is
    written alongside so galleries never have to load video to draw a grid.
    """
    import subprocess
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from app.services.catalog import CLIP_MAX_SECONDS

    shot_uuid = uuid.UUID(shot_id)
    with session_scope() as session:
        shot = session.get(Shot, shot_uuid)
        if shot is None:
            log.warning("clip.shot_missing", shot_id=shot_id)
            return "missing"
        if shot.derivative_at is not None:
            return "already-done"
        if shot.state is not ShotState.UPLOADED or shot.kind != "clip":
            return "not-a-clip"
        original = shot.storage_key
        film_id = str(shot.film_id)

    with TemporaryDirectory() as tmp:
        source = Path(tmp) / "source"
        output = Path(tmp) / "clip.mp4"
        frame = Path(tmp) / "poster.png"
        storage.download_file(original, str(source))

        subprocess.run(
            [
                "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(source),
                "-t", str(CLIP_MAX_SECONDS),
                "-map", "0:v:0", "-map", "0:a:0?",
                "-map_metadata", "-1", "-map_chapters", "-1",
                "-vf", CLIP_SCALE_FILTER,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "96k", "-ac", "2",
                "-movflags", "+faststart",
                str(output),
            ],
            check=True,
            timeout=240,
        )  # fmt: skip
        duration = _probe_seconds(output)
        subprocess.run(
            [
                "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{min(0.5, duration / 2):.2f}", "-i", str(output),
                "-frames:v", "1", str(frame),
            ],
            check=True,
            timeout=60,
        )  # fmt: skip

        poster = io.BytesIO()
        with Image.open(frame) as still:
            rendered = still.convert("RGB")
            rendered.thumbnail(THUMBNAIL_MAX)
            rendered.save(poster, format="WEBP", quality=THUMBNAIL_QUALITY, method=4)

        # Deterministic keys, so a redelivered job overwrites in place.
        storage.upload_file(storage.clip_key(film_id, shot_id), str(output), "video/mp4")
        storage.upload_bytes(storage.poster_key(film_id, shot_id), poster.getvalue(), "image/webp")
        size = output.stat().st_size

    with session_scope() as session:
        session.execute(
            update(Shot)
            .where(Shot.id == shot_uuid, Shot.derivative_at.is_(None))
            .values(derivative_at=func.now(), duration_ms=round(duration * 1000))
        )

    log.info("clip.transcoded", shot_id=shot_id, seconds=round(duration, 2), bytes=size)
    return "ok"


# Fits inside 1280x1280 without upscaling, keeping even dimensions for H.264.
# Portrait and landscape both come out at most 720 on the short side for 16:9.
CLIP_SCALE_FILTER = (
    "scale=w='min(1280,iw)':h='min(1280,ih)'"
    ":force_original_aspect_ratio=decrease:force_divisible_by=2"
)


def _probe_seconds(path: object) -> float:
    import subprocess

    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout  # fmt: skip
    return float(out.strip() or 0)


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
    """Remove every object belonging to a deleted film.

    Idempotent: a rerun over an already-empty prefix deletes nothing and
    returns zero, which is what makes the redelivery safe.
    """
    removed = storage.delete_prefix_sync(storage.film_prefix(film_id))
    log.info("film.objects_purged", film_id=film_id, objects=removed)
    return removed


@celery_app.task(name="app.worker.tasks.purge_deleted_films")
def purge_deleted_films() -> int:
    """Destroy the photographs of films whose grace period has run out.

    The film row itself survives, stamped with ``purged_at``. Deleting it would
    cascade the payments away with it, and a receipt is the host's tax paperwork
    for a service that was genuinely delivered. What goes is everything the
    deletion was actually about: the objects, the shots, and the guest list.
    """
    from datetime import timedelta as _timedelta

    from app.db.models import Film, Guest, Shot

    grace = _timedelta(days=get_settings().deleted_film_grace_days)
    purged = 0

    with session_scope() as session:
        due = session.execute(
            select(Film.id).where(
                Film.deleted_at.isnot(None),
                Film.purged_at.is_(None),
                Film.deleted_at < func.now() - grace,
            )
        ).all()

    for (film_id,) in due:
        # Bytes first. A crash between here and the row delete leaves a film
        # whose objects are already gone, and the next sweep finishes the job;
        # the reverse would leave orphaned photographs nothing points at.
        purge_film_objects(str(film_id))
        with session_scope() as session:
            session.execute(delete(Shot).where(Shot.film_id == film_id))
            session.execute(delete(Guest).where(Guest.film_id == film_id))
            session.execute(
                update(Film)
                .where(Film.id == film_id, Film.purged_at.is_(None))
                .values(purged_at=func.now())
            )
        purged += 1
        log.info("film.purged", film_id=str(film_id))

    if purged:
        log.info("purge.sweep", films=purged)
    return purged


@celery_app.task(name="app.worker.tasks.build_recap_video", bind=True)
def build_recap_video(self, film_id: str) -> None:  # type: ignore[no-untyped-def]
    raise NotImplementedError("Phase 6")


@celery_app.task(
    name="app.worker.tasks.build_export_archive",
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def build_export_archive(self, film_id: str) -> str:  # type: ignore[no-untyped-def]
    return build_export_archive_for_film(film_id)


def build_export_archive_for_film(film_id: str) -> str:
    """ZIP of non-hidden originals. Hidden shots must never leave this way."""
    import zipfile
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from sqlalchemy.orm import selectinload

    from app.db.models import Film, Shot, ShotState
    from app.services import exports

    film_uuid = uuid.UUID(film_id)
    key = storage.export_key(film_id, "originals")

    with session_scope() as session:
        film = session.get(Film, film_uuid)
        if film is None:
            exports.mark_failed_sync(film_id)
            return "missing"
        rows = list(
            session.execute(
                select(Shot)
                .where(
                    Shot.film_id == film_uuid,
                    Shot.state == ShotState.UPLOADED,
                    Shot.hidden_at.is_(None),
                    (Shot.kind == "photo") | Shot.derivative_at.isnot(None),
                )
                .options(selectinload(Shot.guest))
                .order_by(Shot.uploaded_at)
            )
            .scalars()
            .all()
        )
        code = film.code

    try:
        with TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "originals.zip"
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as archive:
                for index, shot in enumerate(rows, start=1):
                    name = (
                        "".join(
                            ch for ch in shot.guest.display_name if ch.isalnum() or ch in " -_"
                        ).strip()
                        or "guest"
                    )
                    stem = f"{index:03d}-{name[:40]}-{str(shot.id)[:8]}"
                    if shot.kind == "clip":
                        # The transcode, not the original: it is the version
                        # with the location metadata stripped.
                        source = storage.clip_key(film_id, str(shot.id))
                        archive.writestr(f"{stem}.mp4", storage.download_bytes(source))
                    else:
                        archive.writestr(f"{stem}.jpg", storage.download_bytes(shot.storage_key))
            storage.upload_file(key, str(zip_path), "application/zip")
    except Exception:
        exports.mark_failed_sync(film_id)
        raise

    exports.mark_ready_sync(film_id)
    log.info("export.ready", film_id=film_id, code=code, shots=len(rows))
    return key


def pending_derivative_ids(limit: int = 100) -> list[str]:
    """Shots that are live but have no derivative yet, for backfills."""
    with session_scope() as session:
        rows = session.execute(
            select(Shot.id)
            .where(
                Shot.state == ShotState.UPLOADED,
                Shot.derivative_at.is_(None),
                Shot.kind == "photo",
            )
            .limit(limit)
        ).all()
    return [str(row[0]) for row in rows]


@celery_app.task(name="app.worker.tasks.send_host_login")
def send_host_login(film_id: str) -> str:
    from app.db.models import Film
    from app.services import notify

    with session_scope() as session:
        film = session.get(Film, uuid.UUID(film_id))
        if film is None or not film.host_email:
            return "missing"
        notify.send_host_login(film)
    return "ok"


@celery_app.task(name="app.worker.tasks.notify_developed_films")
def notify_developed_films() -> int:
    from app.services import notify

    with session_scope() as session:
        return notify.notify_developed_films(session)


@celery_app.task(name="app.worker.tasks.notify_retention_films")
def notify_retention_films() -> int:
    from app.services import notify

    with session_scope() as session:
        return notify.notify_retention_films(session)
