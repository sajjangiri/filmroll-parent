from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from app.services import films as films_service
from app.services import seats, tokens

bearer = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_film(
    code: Annotated[str, Path(min_length=4, max_length=12)], session: DbSession
) -> films_service.FilmView:
    try:
        return await films_service.load_by_code(session, code)
    except films_service.FilmNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "film not found") from None


FilmDep = Annotated[films_service.FilmView, Depends(get_film)]


def _principal(
    credentials: HTTPAuthorizationCredentials | None,
) -> tokens.Principal:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        return tokens.parse(credentials.credentials)
    except tokens.TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from None


async def require_guest(
    view: FilmDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> tokens.Principal:
    principal = _principal(credentials)
    if principal.role != "guest":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "guest token required")
    # A token is scoped to one film. Without this check a guest at one event
    # could act inside somebody else's.
    if principal.film_id != view.film.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "token is not valid for this film")
    return principal


async def _staff(
    view: films_service.FilmView,
    credentials: HTTPAuthorizationCredentials | None,
    session: AsyncSession,
    *,
    allowed: frozenset[str],
) -> tokens.Principal:
    """Shared gate for the film creator, co-hosts, and photographers.

    A seat token names a row that the owner can revoke, so it is re-read here on
    every request rather than trusted for the year the JWT is valid for.
    """
    principal = _principal(credentials)
    if principal.role not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "host token required")
    if principal.film_id != view.film.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "token is not valid for this film")
    if principal.role in tokens.SEAT_ROLES:
        try:
            await seats.load_active(session, film_id=view.film.id, seat_id=principal.seat_id)
        except seats.SeatRevoked:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "this access has been removed") from None
        except seats.SeatError:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "unknown seat") from None
    return principal


async def require_host(
    view: FilmDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: DbSession,
) -> tokens.Principal:
    """Change the film: moderate, reveal, edit caps, buy. Not a photographer."""
    return await _staff(view, credentials, session, allowed=tokens.STAFF_WRITE_ROLES)


async def require_host_owner(
    view: FilmDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: DbSession,
) -> tokens.Principal:
    """The film creator only.

    Guards the things a co-host should not inherit: the owner's email, their
    receipts, and the ability to hand out further access.
    """
    return await _staff(view, credentials, session, allowed=frozenset({"host"}))


async def require_film_staff(
    view: FilmDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: DbSession,
) -> tokens.Principal:
    """Read the inbox and pull originals. Includes the photographer."""
    return await _staff(view, credentials, session, allowed=tokens.STAFF_ROLES)


async def require_bearer(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> tokens.Principal:
    """A valid token, not yet scoped to a film.

    Only for routes that must run when ``get_film`` would 404 — restoring a
    deleted film is the one case, since the film is invisible by design.
    """
    return _principal(credentials)


async def optional_guest(
    view: FilmDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> tokens.Principal | None:
    """A guest token if one was sent, otherwise anonymous.

    The public gallery stays public. A leftover host token in the browser must
    not 401 the page, and must not unlock anyone else's shots on a private film.
    """
    if credentials is None:
        return None
    try:
        principal = tokens.parse(credentials.credentials)
    except tokens.TokenError:
        return None
    if principal.role != "guest" or principal.film_id != view.film.id:
        return None
    return principal


OptionalGuest = Annotated[tokens.Principal | None, Depends(optional_guest)]
GuestPrincipal = Annotated[tokens.Principal, Depends(require_guest)]
BearerPrincipal = Annotated[tokens.Principal, Depends(require_bearer)]
HostPrincipal = Annotated[tokens.Principal, Depends(require_host)]
OwnerPrincipal = Annotated[tokens.Principal, Depends(require_host_owner)]
StaffPrincipal = Annotated[tokens.Principal, Depends(require_film_staff)]
