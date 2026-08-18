from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from app.services import films as films_service
from app.services import tokens

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


async def require_host(
    view: FilmDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> tokens.Principal:
    principal = _principal(credentials)
    if principal.role != "host":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "host token required")
    if principal.film_id != view.film.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "token is not valid for this film")
    return principal


GuestPrincipal = Annotated[tokens.Principal, Depends(require_guest)]
HostPrincipal = Annotated[tokens.Principal, Depends(require_host)]
