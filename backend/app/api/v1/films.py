from __future__ import annotations

import uuid
from typing import Annotated, Any, cast

from fastapi import APIRouter, HTTPException, Path, Request, Response, status

from app.api.deps import (
    BearerPrincipal,
    DbSession,
    FilmDep,
    GuestPrincipal,
    HostPrincipal,
    OptionalGuest,
    OwnerPrincipal,
    StaffPrincipal,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import Film, FilmSeat, Shot
from app.schemas import (
    CheckoutRequest,
    CheckoutResponse,
    CommitResponse,
    ExportResponse,
    FilmCreate,
    FilmCreated,
    FilmDeleted,
    FilmPublic,
    FilmUpdate,
    GalleryPhoto,
    GalleryResponse,
    HostAccount,
    JoinRequest,
    JoinResponse,
    MagicSessionRequest,
    PaymentReceipt,
    PaymentsResponse,
    PushTokenRequest,
    RecoverRequest,
    ReportRequest,
    ReportResponse,
    ReserveRequest,
    ReserveResponse,
    ReviewPhoto,
    ReviewResponse,
    SeatClaimed,
    SeatClaimRequest,
    SeatCreate,
    SeatCreated,
    SeatPublic,
    SeatsResponse,
    SetPinRequest,
)
from app.services import (
    billing,
    catalog,
    exports,
    notify,
    pins,
    printcards,
    push,
    qrcodes,
    ratelimit,
    reports,
    seats,
    storage,
    stripe_billing,
    tokens,
)
from app.services import films as films_service
from app.services.dispatch import enqueue_after_commit

router = APIRouter(prefix="/v1/films", tags=["films"])
log = get_logger(__name__)


def _client_ip(request: Request) -> str:
    """Best-effort caller identity for rate limiting.

    X-Forwarded-For is spoofable unless a trusted proxy rewrites it, so this is
    a speed bump rather than an authorisation decision. It is only ever used to
    slow down joins, never to grant access.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


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
        entitled_guest_cap=film.entitled_guest_cap,
        keep_forever=film.keep_forever,
        unlimited_shots=film.unlimited_shots,
        video_pack=film.video_pack,
        clips_per_guest=catalog.CLIPS_PER_GUEST if film.video_pack else 0,
        clip_max_seconds=catalog.CLIP_MAX_SECONDS,
        instant_reveal=film.instant_reveal,
        shared_gallery=film.shared_gallery,
        storage_until=film.storage_until,
        guest_count=await films_service.guest_count(session, film.id),
        shot_count=len(await films_service.visible_shots(session, film.id)),
        requires_pin=film.join_pin_hash is not None,
        join_url=qrcodes.join_url(film.code),
    )


@router.post("", response_model=FilmCreated, status_code=status.HTTP_201_CREATED)
async def create_film(payload: FilmCreate, session: DbSession) -> FilmCreated:
    try:
        film = await films_service.create_film(
            session,
            title=payload.title,
            event_type=payload.event_type,
            closes_at=payload.closes_at,
            reveal_at=payload.reveal_at,
            instant_reveal=payload.instant_reveal,
            shared_gallery=payload.shared_gallery,
            shot_limit=payload.shot_limit,
            guest_cap=payload.guest_cap,
            host_email=payload.host_email,
        )
    except films_service.InvalidEmail:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid email") from None
    view = await films_service.load_by_id(session, film.id)
    public = await _to_public(
        session, view.film, is_developed=view.is_developed, is_closed=view.is_closed
    )
    if film.host_email:
        notify.send_host_login(film)
    log.info("film.created", film_id=str(film.id), code=film.code)
    return FilmCreated(film=public, host_token=tokens.issue_host_token(film.id))


@router.get("/{code}", response_model=FilmPublic)
async def get_film(view: FilmDep, session: DbSession) -> FilmPublic:
    return await _to_public(
        session, view.film, is_developed=view.is_developed, is_closed=view.is_closed
    )


@router.post("/{code}/join", response_model=JoinResponse, status_code=status.HTTP_201_CREATED)
async def join(
    payload: JoinRequest, view: FilmDep, session: DbSession, request: Request
) -> JoinResponse:
    if view.is_closed:
        raise HTTPException(status.HTTP_410_GONE, "this film has closed")

    settings = get_settings()
    if not await ratelimit.allow(
        "join",
        f"{view.film.code}:{_client_ip(request)}",
        limit=settings.rate_limit_join_per_hour,
        window_seconds=3600,
    ):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many joins, slow down")

    # Checked after the limiter on purpose: a wrong guess spends one of the
    # twenty attempts this address gets per hour, which is what keeps a
    # four-digit secret meaningful.
    if not pins.matches(view.film.join_pin_hash, payload.join_pin):
        log.info("join.pin_rejected", film_id=str(view.film.id), ip=_client_ip(request))
        raise HTTPException(status.HTTP_403_FORBIDDEN, "wrong PIN for this film")

    try:
        guest = await films_service.join_film(session, view.film, payload.display_name)
    except films_service.GuestCapReached:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "this film has reached its guest limit"
        ) from None

    remaining = await films_service.shots_remaining(session, film=view.film, guest_id=guest.id)
    return JoinResponse(
        guest_id=guest.id,
        guest_token=tokens.issue_guest_token(view.film.id, guest.id),
        display_name=guest.display_name,
        shots_remaining=remaining,
        clips_remaining=await films_service.clips_remaining(
            session, film=view.film, guest_id=guest.id
        ),
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

    # Keyed on the guest, not the address, because a venue puts every phone
    # behind one NAT and an address-based limit would throttle the whole party.
    if not await ratelimit.allow(
        "reserve",
        str(principal.guest_id),
        limit=get_settings().rate_limit_reserve_per_minute,
        window_seconds=60,
    ):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many uploads, slow down")

    try:
        key, already = await films_service.reserve_shot(
            session,
            film=view.film,
            guest_id=principal.guest_id,
            shot_id=payload.shot_id,
            content_type=payload.content_type,
            kind=payload.kind,
        )
    except films_service.ShotLimitReached:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "you have used every shot on this roll"
        ) from None
    except films_service.ClipLimitReached:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "you have used every clip on this roll"
        ) from None
    except films_service.VideoPackRequired:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED, "this film does not include video clips"
        ) from None
    except films_service.UploadTypeRejected as exc:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"unsupported clip type: {exc}"
        ) from None

    # Sign for the type the row holds, not the one in this request: a replay of
    # an existing id must get a URL that matches the object it will overwrite.
    content_type = await films_service.shot_content_type(session, payload.shot_id)
    upload_url = await storage.presign_put(key, content_type)
    return ReserveResponse(
        shot_id=payload.shot_id,
        upload_url=upload_url,
        storage_key=key,
        expires_in=get_settings().upload_url_ttl_seconds,
        already_reserved=already,
        content_type=content_type,
        **await _allowances(session, view.film, principal.guest_id),
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
    except films_service.ShotExpired:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "this shot expired, reserve a new one"
        ) from None
    except films_service.UploadTooLarge as exc:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"upload is too large: {exc}"
        ) from None
    except films_service.UploadTypeRejected as exc:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"unsupported upload type: {exc}"
        ) from None

    # Held until this request's transaction commits. Dispatching inline would
    # let a worker look for a row that is not visible yet.
    task = "transcode_clip" if shot.kind == "clip" else "generate_derivatives"
    enqueue_after_commit(session, f"app.worker.tasks.{task}", str(shot.id))

    return CommitResponse(
        shot_id=shot.id,
        state=str(shot.state.value),
        **await _allowances(session, view.film, principal.guest_id),
    )


async def _allowances(session: DbSession, film: Film, guest_id: uuid.UUID) -> dict[str, int]:
    return {
        "shots_remaining": await films_service.shots_remaining(
            session, film=film, guest_id=guest_id
        ),
        "clips_remaining": await films_service.clips_remaining(
            session, film=film, guest_id=guest_id
        ),
    }


async def _media(shot: Shot) -> dict[str, Any]:
    """URLs for one gallery tile. A clip is served as its transcode, never the original."""
    if shot.kind == "clip":
        film_id, shot_id = str(shot.film_id), str(shot.id)
        return {
            "kind": "clip",
            "url": await storage.presign_get(storage.clip_key(film_id, shot_id)),
            "poster_url": await storage.presign_get(storage.poster_key(film_id, shot_id)),
            "duration_ms": shot.duration_ms,
        }
    media: dict[str, Any] = {"kind": "photo", "url": await storage.presign_get(shot.storage_key)}
    if shot.derivative_at is not None:
        media["display_url"] = await storage.presign_get(
            storage.display_key(str(shot.film_id), str(shot.id))
        )
    return media


@router.get("/{code}/qr.svg", response_class=Response)
async def join_qr(view: FilmDep) -> Response:
    """QR code for the printed card and the host screen.

    Served from here rather than a third-party image API. The join URL names a
    private event, and posting every one of them to an outside service hands
    over a guest list nobody agreed to share.
    """
    svg = qrcodes.join_qr_svg(view.film.code)
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={
            # The code is fixed for the life of the film, so this is safe to keep.
            "Cache-Control": "public, max-age=3600",
            "Content-Disposition": f'inline; filename="filmroll-{view.film.code}.svg"',
        },
    )


@router.get("/{code}/qr.png", response_class=Response)
async def join_qr_png(view: FilmDep) -> Response:
    """Raster twin of ``qr.svg`` for the native app, whose ``Image`` cannot draw SVG."""
    png = qrcodes.join_qr_png(view.film.code, scale=10)
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Disposition": f'inline; filename="filmroll-{view.film.code}.png"',
        },
    )


@router.get("/{code}/gallery", response_model=GalleryResponse)
async def gallery(view: FilmDep, session: DbSession, guest: OptionalGuest) -> GalleryResponse:
    """The reveal boundary.

    Before a film develops this returns a count and nothing else. No URL is
    minted, so there is nothing to leak even if the response is inspected.

    A private film still develops on schedule, but signed URLs are only minted
    for the calling guest's own shots. The host inbox is how the couple sees
    the whole roll.
    """
    waiting = await films_service.visible_shots(session, view.film.id)
    if not view.is_developed:
        return GalleryResponse(is_developed=False, shot_count=len(waiting), photos=[])

    if not view.film.shared_gallery:
        if guest is None:
            return GalleryResponse(is_developed=True, shot_count=len(waiting), photos=[])
        shots = await films_service.visible_shots(session, view.film.id, guest_id=guest.guest_id)
    else:
        shots = waiting

    photos = [
        GalleryPhoto(
            shot_id=shot.id,
            guest_name=shot.guest.display_name,
            uploaded_at=shot.uploaded_at,
            **await _media(shot),
        )
        for shot in shots
    ]
    return GalleryResponse(is_developed=True, shot_count=len(photos), photos=photos)


@router.post("/{code}/reveal", response_model=FilmPublic)
async def reveal(view: FilmDep, principal: HostPrincipal, session: DbSession) -> FilmPublic:
    await films_service.reveal_now(session, view.film)
    enqueue_after_commit(session, "app.worker.tasks.notify_developed_films")
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


@router.post("/{code}/shots/{shot_id}/unhide", status_code=status.HTTP_204_NO_CONTENT)
async def unhide_shot(
    shot_id: uuid.UUID, view: FilmDep, principal: HostPrincipal, session: DbSession
) -> None:
    await films_service.unhide_shot(session, film=view.film, shot_id=shot_id)


@router.post("/{code}/shots/{shot_id}/report", response_model=ReportResponse)
async def report_shot(
    shot_id: uuid.UUID,
    payload: ReportRequest,
    view: FilmDep,
    principal: GuestPrincipal,
    session: DbSession,
) -> ReportResponse:
    """Flag a photo for the host.

    Guest-scoped rather than open to anyone holding the gallery link, so the
    count reflects people who were actually at the event. It never hides
    anything; see ``ShotReport`` for why that is deliberate.
    """
    try:
        total = await reports.report_shot(
            session,
            film_id=view.film.id,
            shot_id=shot_id,
            guest_id=principal.guest_id,
            reason=payload.reason,
        )
    except reports.UnknownShot:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "shot not found") from None

    return ReportResponse(shot_id=shot_id, report_count=total)


@router.put("/{code}/push-token", status_code=status.HTTP_204_NO_CONTENT)
async def register_push_token(
    payload: PushTokenRequest,
    view: FilmDep,
    principal: GuestPrincipal,
    session: DbSession,
) -> None:
    """Where to ping this guest when the film develops.

    Hosts already get email. Instant films never send this notice: they are
    born developed, and "your film is ready" would land as the host creates it.
    """
    try:
        await push.upsert_token(
            session,
            guest_id=principal.guest_id,
            film_id=view.film.id,
            token=payload.token,
            locale=payload.locale,
        )
    except push.InvalidToken as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    except push.InvalidLocale as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None


@router.delete("/{code}/shots/{shot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def retract_shot(
    shot_id: uuid.UUID, view: FilmDep, principal: GuestPrincipal, session: DbSession
) -> None:
    try:
        await films_service.retract_shot(
            session, film=view.film, guest_id=principal.guest_id, shot_id=shot_id
        )
    except films_service.ShotNotOwned:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "shot not found") from None


@router.patch("/{code}", response_model=FilmPublic)
async def update_film(
    payload: FilmUpdate, view: FilmDep, principal: HostPrincipal, session: DbSession
) -> FilmPublic:
    try:
        await films_service.update_film(
            session,
            view.film,
            closes_at=payload.closes_at,
            reveal_at=payload.reveal_at,
            shot_limit=payload.shot_limit,
            guest_cap=payload.guest_cap,
            host_email=payload.host_email,
            shared_gallery=payload.shared_gallery,
        )
    except films_service.CapBelowHeadcount as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    except films_service.CapAboveEntitlement as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(exc)) from None
    except films_service.LimitBelowUse as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    except films_service.RevealLocked as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    except films_service.InvalidEmail:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid email") from None

    if payload.host_email:
        notify.send_host_login(view.film)

    refreshed = await films_service.load_by_id(session, view.film.id)
    return await _to_public(
        session,
        refreshed.film,
        is_developed=refreshed.is_developed,
        is_closed=refreshed.is_closed,
    )


@router.get("/{code}/review", response_model=ReviewResponse)
async def review(view: FilmDep, principal: StaffPrincipal, session: DbSession) -> ReviewResponse:
    """Host inbox. Photos are visible here before the film develops.

    That is the whole point of moderation: a host must be able to hide a shot
    before a hundred phones see it at reveal.
    """
    shots = await films_service.review_shots(session, view.film.id)
    report_counts = await reports.counts_for_film(session, view.film.id)
    photos = [
        ReviewPhoto(
            shot_id=shot.id,
            guest_name=shot.guest.display_name,
            uploaded_at=shot.uploaded_at,
            hidden=shot.hidden_at is not None,
            report_count=report_counts.get(shot.id, 0),
            **await _media(shot),
        )
        for shot in shots
    ]
    hidden_count = sum(1 for photo in photos if photo.hidden)
    # A reported shot that is still visible is the only thing here that needs
    # the host to do something, so it is counted separately from the rest.
    reported_count = sum(1 for photo in photos if photo.report_count > 0 and not photo.hidden)
    return ReviewResponse(
        shot_count=len(photos),
        hidden_count=hidden_count,
        reported_count=reported_count,
        photos=photos,
    )


@router.get("/{code}/cards.pdf", response_class=Response)
async def join_cards(view: FilmDep) -> Response:
    """A4 PDF of table cards and larger signage. Public like the QR itself."""
    pdf = printcards.join_cards_pdf(code=view.film.code, title=view.film.title)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="filmroll-{view.film.code}-cards.pdf"',
            "Cache-Control": "private, max-age=300",
        },
    )


@router.post("/{code}/export", response_model=ExportResponse)
async def start_export(
    view: FilmDep, principal: StaffPrincipal, session: DbSession
) -> ExportResponse:
    """Build a ZIP of clean originals. Runs on the media worker.

    Hidden shots are omitted. The zip never passes through this process.
    """
    shots = await films_service.visible_shots(session, view.film.id)
    await exports.mark_pending(str(view.film.id))
    enqueue_after_commit(session, "app.worker.tasks.build_export_archive", str(view.film.id))
    return ExportResponse(status=exports.PENDING, shot_count=len(shots))


@router.get("/{code}/export", response_model=ExportResponse)
async def get_export(
    view: FilmDep, principal: StaffPrincipal, session: DbSession
) -> ExportResponse:
    film_id = str(view.film.id)
    state = await exports.status(film_id)
    shots = await films_service.visible_shots(session, view.film.id)
    url = None
    if state == exports.READY:
        key = storage.export_key(film_id, "originals")
        if await storage.object_exists(key):
            url = await storage.presign_get(key)
        else:
            state = "idle"
    return ExportResponse(status=state, shot_count=len(shots), download_url=url)


@router.post("/{code}/checkout", response_model=CheckoutResponse)
async def checkout(
    payload: CheckoutRequest,
    view: FilmDep,
    principal: HostPrincipal,
    session: DbSession,
) -> CheckoutResponse:
    """Start Stripe Checkout (or the local fake) for a higher guest cap or add-on.

    The entitlement is granted only after payment: fake Checkout applies it
    immediately so local development has no Stripe dependency; production waits
    for the signed webhook.
    """
    try:
        tier, addon = billing.resolve_item(payload.tier_id, payload.addon_id)
    except catalog.UnknownTier:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown tier") from None
    except catalog.UnknownAddon:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown add-on") from None
    except billing.BillingError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None

    try:
        if tier is not None:
            amount = billing.quote_tier(view.film, tier)
        else:
            assert addon is not None
            amount = billing.quote_addon(view.film, addon)
    except (billing.AlreadyEntitled, billing.AlreadyPurchased) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None

    kind = billing.kind_for(tier=tier, addon=addon)
    description = stripe_billing.describe_purchase(tier=tier, addon=addon)
    try:
        session_id, url, fake = stripe_billing.create_checkout_session(
            film=view.film,
            kind=kind,
            amount_cents=amount,
            description=description,
            guest_cap=tier.guest_cap if tier else None,
            addon_id=addon.id if addon else None,
        )
    except billing.CheckoutNotConfigured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "billing is not configured"
        ) from None
    except stripe_billing.StripeError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None

    await billing.open_payment(
        session,
        film=view.film,
        provider_session_id=session_id,
        kind=kind,
        guest_cap=tier.guest_cap if tier else None,
        amount_cents=amount,
        currency=catalog.CURRENCY,
    )
    if fake:
        await billing.fulfill_session(session, provider_session_id=session_id)

    log.info(
        "billing.checkout",
        film_id=str(view.film.id),
        kind=kind,
        amount_cents=amount,
        fake=fake,
    )
    return CheckoutResponse(url=url, fake=fake, amount_cents=amount)


@router.get("/{code}/payments", response_model=PaymentsResponse)
async def payments(
    view: FilmDep,
    principal: OwnerPrincipal,
    session: DbSession,
) -> PaymentsResponse:
    """Receipts for this film. Host only — this is the host's tax paperwork.

    Amounts come from our own rows rather than Stripe so the page still renders
    during a Stripe outage, and so fake Checkout has something to show locally.
    """
    rows = await billing.payments_for_film(session, view.film.id)
    receipts = [
        PaymentReceipt(
            id=row.id,
            kind=row.kind,
            label=catalog.describe_kind(row.kind),
            status=row.status,
            amount_cents=row.amount_cents,
            tax_cents=row.tax_cents,
            total_cents=row.total_cents if row.total_cents is not None else row.amount_cents,
            refunded_cents=row.refunded_cents,
            currency=row.currency,
            receipt_url=row.receipt_url,
            customer_email=row.customer_email,
            created_at=row.created_at,
            paid_at=row.paid_at,
            refunded_at=row.refunded_at,
        )
        for row in rows
    ]
    return PaymentsResponse(
        payments=receipts,
        total_paid_cents=sum(r.total_cents for r in receipts),
        total_tax_cents=sum(r.tax_cents for r in receipts),
        total_refunded_cents=sum(r.refunded_cents for r in receipts),
        currency=catalog.CURRENCY,
    )


@router.get("/{code}/host/account", response_model=HostAccount)
async def host_account(view: FilmDep, principal: OwnerPrincipal) -> HostAccount:
    return HostAccount(email=view.film.host_email, unlimited_shots=view.film.unlimited_shots)


@router.put("/{code}/pin", response_model=FilmPublic)
async def set_pin(
    payload: SetPinRequest, view: FilmDep, principal: HostPrincipal, session: DbSession
) -> FilmPublic:
    """Require a PIN to join. Guests already holding a camera keep it."""
    try:
        await films_service.set_join_pin(session, view.film, payload.pin)
    except pins.InvalidPin as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    return await _to_public(
        session, view.film, is_developed=view.is_developed, is_closed=view.is_closed
    )


@router.delete("/{code}/pin", response_model=FilmPublic)
async def clear_pin(view: FilmDep, principal: HostPrincipal, session: DbSession) -> FilmPublic:
    await films_service.set_join_pin(session, view.film, None)
    return await _to_public(
        session, view.film, is_developed=view.is_developed, is_closed=view.is_closed
    )


@router.delete("/{code}", response_model=FilmDeleted)
async def delete_film(view: FilmDep, principal: OwnerPrincipal, session: DbSession) -> FilmDeleted:
    """Take the film down now; destroy the photographs after a grace period.

    Guests, the gallery, and every co-host lose it immediately. The objects are
    kept for `DELETED_FILM_GRACE_DAYS` because for most of these events this is
    the only copy of the photographs that exists.
    """
    purge_at = await films_service.soft_delete(session, view.film)
    return FilmDeleted(code=view.film.code, deleted_at=view.film.deleted_at, purge_at=purge_at)


@router.post("/{code}/restore", response_model=FilmPublic)
async def restore_film(
    code: Annotated[str, Path(min_length=4, max_length=12)],
    principal: BearerPrincipal,
    session: DbSession,
) -> FilmPublic:
    """Undo a delete inside the grace window.

    Cannot use ``FilmDep``: a deleted film is a 404 to everything else, which is
    the whole point. Every failure here answers 404 rather than 403, because
    confirming that a deleted film exists is itself the thing being protected.
    """
    try:
        view = await films_service.load_by_code(session, code, include_deleted=True)
    except films_service.FilmNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "film not found") from None
    if principal.role != "host" or principal.film_id != view.film.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "film not found")

    try:
        await films_service.restore(session, view.film)
    except films_service.FilmAlreadyPurged:
        raise HTTPException(
            status.HTTP_410_GONE, "the grace period has passed and the photos are gone"
        ) from None

    refreshed = await films_service.load_by_id(session, view.film.id)
    return await _to_public(
        session,
        refreshed.film,
        is_developed=refreshed.is_developed,
        is_closed=refreshed.is_closed,
    )


@router.post("/{code}/seats", response_model=SeatCreated, status_code=status.HTTP_201_CREATED)
async def create_seat(
    payload: SeatCreate,
    view: FilmDep,
    principal: OwnerPrincipal,
    session: DbSession,
) -> SeatCreated:
    """Let a partner, planner, or photographer into this film.

    Returns a link the owner sends however they like. The link is short-lived
    and is exchanged for the durable token, so a screenshot of a message thread
    is not a year of access on its own.
    """
    try:
        seat = await seats.create_seat(
            session, film_id=view.film.id, role=payload.role, label=payload.label
        )
    except seats.TooManySeats as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    except seats.SeatError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None

    invite = tokens.issue_seat_invite(view.film.id, seat.id)
    base = get_settings().public_web_url.rstrip("/")
    return SeatCreated(
        seat=_seat_public(seat),
        invite_token=invite,
        invite_url=f"{base}/f/{view.film.code}/host?seat={invite}",
    )


@router.get("/{code}/seats", response_model=SeatsResponse)
async def list_seats(view: FilmDep, principal: OwnerPrincipal, session: DbSession) -> SeatsResponse:
    rows = await seats.active_seats(session, view.film.id)
    return SeatsResponse(seats=[_seat_public(seat) for seat in rows])


@router.delete("/{code}/seats/{seat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_seat(
    seat_id: uuid.UUID,
    view: FilmDep,
    principal: OwnerPrincipal,
    session: DbSession,
) -> None:
    """Immediate. Authorisation re-reads the seat row on every request."""
    try:
        await seats.revoke(session, film_id=view.film.id, seat_id=seat_id)
    except seats.UnknownSeat:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "seat not found") from None


@router.post("/{code}/seats/claim", response_model=SeatClaimed)
async def claim_seat(payload: SeatClaimRequest, view: FilmDep, session: DbSession) -> SeatClaimed:
    """Exchange an invite link for this device's own durable token."""
    try:
        film_id, seat_id = tokens.parse_seat_invite(payload.invite_token)
    except tokens.TokenError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired invite") from None
    if film_id != view.film.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invite is for another film") from None

    try:
        seat = await seats.claim(session, film_id=view.film.id, seat_id=seat_id)
    except seats.SeatRevoked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "this access has been removed") from None
    except seats.SeatError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "seat not found") from None

    role = cast(tokens.SeatRole, seat.role)
    return SeatClaimed(
        token=tokens.issue_seat_token(view.film.id, seat.id, role),
        role=seat.role,
        label=seat.label,
        film=await _to_public(
            session, view.film, is_developed=view.is_developed, is_closed=view.is_closed
        ),
    )


def _seat_public(seat: FilmSeat) -> SeatPublic:
    return SeatPublic(
        id=seat.id,
        role=seat.role,
        label=seat.label,
        created_at=seat.created_at,
        claimed_at=seat.claimed_at,
    )


@router.post("/{code}/host/recover", status_code=status.HTTP_204_NO_CONTENT)
async def recover_host(payload: RecoverRequest, view: FilmDep, request: Request) -> None:
    """Always 204. Whether the email matches is not something a stranger should learn."""
    settings = get_settings()
    if not await ratelimit.allow(
        "recover",
        f"{view.film.code}:{_client_ip(request)}",
        limit=settings.rate_limit_recover_per_hour,
        window_seconds=3600,
    ):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many recovery attempts")

    try:
        email = notify.normalize_email(payload.email)
    except ValueError:
        return
    if view.film.host_email and view.film.host_email == email:
        notify.send_host_login(view.film)


@router.post("/{code}/host/session", response_model=FilmCreated)
async def consume_magic_link(
    payload: MagicSessionRequest, view: FilmDep, session: DbSession
) -> FilmCreated:
    try:
        film_id, email = tokens.parse_magic(payload.magic_token)
    except tokens.TokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired link") from None
    if film_id != view.film.id or not view.film.host_email or view.film.host_email != email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired link") from None
    public = await _to_public(
        session,
        view.film,
        is_developed=view.is_developed,
        is_closed=view.is_closed,
    )
    return FilmCreated(film=public, host_token=tokens.issue_host_token(view.film.id))
