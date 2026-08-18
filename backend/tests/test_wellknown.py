"""Apple associated-domain file.

The App Clip cannot be invoked from a QR until this is live on the production
domain. The contents are placeholders until App Store Connect issues a Team ID.
"""

from __future__ import annotations

from httpx import AsyncClient

from app.core.config import get_settings


async def test_apple_app_site_association_is_json_without_auth(client: AsyncClient) -> None:
    response = await client.get("/.well-known/apple-app-site-association")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    settings = get_settings()
    app_id = f"TEAMID.{settings.ios_bundle_id}"
    clip_id = f"TEAMID.{settings.ios_clip_bundle_id}"
    assert app_id in body["applinks"]["details"][0]["appIDs"]
    assert clip_id in body["appclips"]["apps"]
    assert any(item["/"] == "/f/*" for item in body["applinks"]["details"][0]["components"])
