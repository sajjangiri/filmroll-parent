"""Apple associated-domain file and Android App Links.

The App Clip cannot be invoked from a QR until this is live on the production
domain. The contents are placeholders until App Store Connect issues a Team ID.
"""

from __future__ import annotations

import pytest
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


async def test_asset_links_empty_until_a_signing_key_is_configured(client: AsyncClient) -> None:
    response = await client.get("/.well-known/assetlinks.json")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == []


async def test_asset_links_names_the_package_and_every_fingerprint(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "android_cert_sha256", "aa:bb:cc, DD:EE:FF")

    body = (await client.get("/.well-known/assetlinks.json")).json()
    assert body[0]["relation"] == ["delegate_permission/common.handle_all_urls"]
    assert body[0]["target"] == {
        "namespace": "android_app",
        "package_name": settings.android_package,
        "sha256_cert_fingerprints": ["AA:BB:CC", "DD:EE:FF"],
    }
