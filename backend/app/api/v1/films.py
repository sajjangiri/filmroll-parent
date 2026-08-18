from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession, FilmDep, GuestPrincipal, HostPrincipal
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import Film
from app.schemas import (
    CommitResponse,
    FilmCreate,
    FilmCreated,
    FilmPublic,
    GalleryPhoto,
    GalleryResponse,
    JoinRequest,
    JoinResponse,
    ReserveRequest,
    ReserveResponse,
)
from app.services import films as films_service
from app.services import storage, tokens
from app.services.dispatch import enqueue_after_commit

router = APIRouter(prefix="/v1/films", tags=["films"])
log = get_logger(__name__)


async def _to_public(
    session: DbSession, film: Film, *, is_developed: bool, is_closed: bool
) -> FilmPublic:
    return FilmPublic(
        code=film.code,
        title=film.title,
        event_type=film.event_type,
        closes_at=film.closes_at,
        reveal_at=film.reveal_at,
        is_developed=is_developed,
        is_closed=is_closed,
        shot_limit=film.shot_limit,
        guest_cap=film.guest_cap,
        guest_count=await films_service.guest_count(session, film.id),
    )


@router.post("", response_model=FilmCreated, status_code=status.HTTP_201_CREATED)
async def create_film(payload: FilmCreate, session: DbSession) -> FilmCreated:
    film = await films_service.create_film(
        session,
        title=payload.title,
        event_type=payload.event_type,
        closes_at=payload.closes_at,
        reveal_at=payload.reveal_at,
        shot_limit=payload.shot_limit,
        guest_cap=payload.guest_cap,
    )
    view = await films_service.load_by_id(session, film.id)
    public = await _to_public(
        session, view.film, is_developed=view.is_developed, is_closed=view.is_closed
    )
    log.info("film.created", film_id=str(film.id), code=film.code)
    return FilmCreated(film=public, host_token=tokens.issue_host_token(film.id))


@router.get("/{code}", response_model=FilmPublic)
async def get_film(view: FilmDep, session: DbSession) -> FilmPublic:
    return await _to_public(
        session, view.film, is_developed=view.is_developed, is_closed=view.is_closed
    )


@router.post("/{code}/join", response_model=JoinResponse, status_code=status.HTTP_201_CREATED)
async def join(payload: JoinRequest, view: FilmDep, session: DbSession) -> JoinResponse:
    if view.is_closed:
        raise HTTPException(status.HTTP_410_GONE, "this film has closed")
    try:
        guest = await films_service.join_film(session, view.film, payload.display_name)
    except films_service.GuestCapReached:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "this film has reached its guest limit"
        ) from None

    remaining = await films_service.shots_remaining(
        session, film=view.film, guest_id=guest.id
    )
    return JoinResponse(
        guest_id=guest.id,
        guest_token=tokens.issue_guest_token(view.film.id, guest.id),
        display_name=guest.display_name,
        shots_remaining=remaining,
    )


@router.post("/{code}/shots/reserve", response_model=ReserveResponse)
async def reserve_shot(
    payload: ReserveRequest,
    view: FilmDep,
    principal: GuestPrincipal,
    session: DbSession,
) -> ReserveResponse:
    """Claim a slot and hand back a presigned upload URL.

    Photo bytes go from the device straight to object storage. They never pass
    through this process, which is what lets a single small container carry an
    entire wedding.
    """
    if view.is_closed:
        raise HTTPException(status.HTTP_410_GONE, "this film has closed")

    try:
        key, already = await films_service.reserve_shot(
            session,
            film=view.film,
            guest_id=principal.guest_id,
            shot_id=payload.shot_id,
            content_type=payload.content_type,
        )
    except films_service.ShotLimitReached:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "you have used every shot on this roll"
        ) from None

    upload_url = await storage.presign_put(key, payload.content_type)
    remaining = await films_service.shots_remaining(
        session, film=view.film, guest_id=principal.guest_id
    )
    return ReserveResponse(
        shot_id=payload.shot_id,
        upload_url=upload_url,
        storage_key=key,
        expires_in=get_settings().upload_url_ttl_seconds,
        already_reserved=already,
        shots_remaining=remaining,
    )


@router.post("/{code}/shots/{shot_id}/commit", response_model=CommitResponse)
async def commit_shot(
    shot_id: uuid.UUID,
    view: FilmDep,
    principal: GuestPrincipal,
    session: DbSession,
) -> CommitResponse:
    try:
        shot = await films_service.commit_shot(
            session, film=view.film, guest_id=principal.guest_id, shot_id=shot_id
        )
    except films_service.ShotNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "shot not found") from None
    except films_service.UploadMissing:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "no uploaded file found for this shot"
        ) from None

    # Held until this request's transaction commits. Dispatching inline would
    # let a worker look for a row that is not visible yet.
    enqueue_after_commit(session, "app.worker.tasks.generate_derivatives", str(shot.id))

    remaining = await films_service.shots_remaining(
        session, film=view.film, guest_id=principal.guest_id
    )
    return CommitResponse(
        shot_id=shot.id, state=str(shot.state.value), shots_remaining=remaining
    )


@router.get("/{code}/gallery", response_model=GalleryResponse)
async def gallery(view: FilmDep, session: DbSession) -> GalleryResponse:
    """The reveal boundary.

    Before a film develops this returns a count and nothing else. No URL is
    minted, so there is nothing to leak even if the response is inspected.
    """
    shots = await films_service.visible_shots(session, view.film.id)

    if not view.is_developed:
        return GalleryResponse(is_developed=False, shot_count=len(shots), photos=[])

    photos = [
        GalleryPhoto(
            shot_id=shot.id,
            guest_name=shot.guest.display_name,
            uploaded_at=shot.uploaded_at,
            url=await storage.presign_get(shot.storage_key),
        )
        for shot in shots
    ]
    return GalleryResponse(is_developed=True, shot_count=len(photos), photos=photos)


@router.post("/{code}/reveal", response_model=FilmPublic)
async def reveal(view: FilmDep, principal: HostPrincipal, session: DbSession) -> FilmPublic:
    await films_service.reveal_now(session, view.film)
    refreshed = await films_service.load_by_id(session, view.film.id)
    return await _to_public(
        session,
        refreshed.film,
        is_developed=refreshed.is_developed,
        is_closed=refreshed.is_closed,
    )


@router.post("/{code}/shots/{shot_id}/hide", status_code=status.HTTP_204_NO_CONTENT)
async def hide_shot(
    shot_id: uuid.UUID, view: FilmDep, principal: HostPrincipal, session: DbSession
) -> None:
    await films_service.hide_shot(session, film=view.film, shot_id=shot_id)
