"""Apple associated-domain and Android App Links files.

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


@router.get("/.well-known/assetlinks.json")
async def android_asset_links() -> JSONResponse:
    """Lets Android open ``/f/{code}`` links in the app when it is installed.

    Android checks this once at install time. With no fingerprints configured the
    list is empty, which verifies nothing and leaves every link on the PWA.
    """
    settings = get_settings()
    fingerprints = [
        value.strip().upper() for value in settings.android_cert_sha256.split(",") if value.strip()
    ]
    statements = (
        [
            {
                "relation": ["delegate_permission/common.handle_all_urls"],
                "target": {
                    "namespace": "android_app",
                    "package_name": settings.android_package,
                    "sha256_cert_fingerprints": fingerprints,
                },
            }
        ]
        if fingerprints
        else []
    )
    return JSONResponse(
        statements,
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=3600"},
    )
