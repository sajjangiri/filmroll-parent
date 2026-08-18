"""Apple associated-domain files.

Served at the well-known URL with application/json and no redirect. An App
Clip cannot be invoked from a QR until this file is live on the production
domain and an Advanced App Clip Experience exists in App Store Connect.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import get_settings

router = APIRouter(tags=["well-known"])


@router.get("/.well-known/apple-app-site-association")
async def apple_app_site_association() -> JSONResponse:
    settings = get_settings()
    team = settings.apple_team_id or "TEAMID"
    app_id = f"{team}.{settings.ios_bundle_id}"
    clip_id = f"{team}.{settings.ios_clip_bundle_id}"
    return JSONResponse(
        {
            "applinks": {
                "apps": [],
                "details": [
                    {
                        "appIDs": [app_id],
                        "components": [{"/": "/f/*"}],
                    }
                ],
            },
            "appclips": {"apps": [clip_id]},
        },
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=3600"},
    )
