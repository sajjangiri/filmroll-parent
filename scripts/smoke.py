#!/usr/bin/env python3
"""End-to-end smoke test of the core loop against a running local stack.

Walks the path a real event takes: create, join, reserve, upload straight to
storage, commit, confirm the gallery stays sealed, reveal, then confirm the
photo is reachable through a signed URL.

Usage:  python3 scripts/smoke.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta

API = "http://localhost:8000"
STORAGE = "http://localhost:9000"

# Smallest structurally valid JPEG: SOI, APP0/JFIF, EOI.
JPEG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffd9")

passed = 0
failed = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}  {detail}")


def request(
    method: str, url: str, *, body: object = None, token: str | None = None,
    raw: bytes | None = None, content_type: str | None = None,
) -> tuple[int, object]:
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(url, data=data, method=method)
    if raw is None and body is not None:
        req.add_header("Content-Type", "application/json")
    if content_type:
        req.add_header("Content-Type", content_type)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, _decode(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, _decode(exc.read())


def _decode(payload: bytes) -> object:
    """Return parsed JSON, or the raw bytes when the body is binary."""
    try:
        return json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return payload


def main() -> int:
    now = datetime.now(UTC)
    print("\nCreate a film that has not developed yet")
    status, created = request(
        "POST", f"{API}/v1/films",
        body={
            "title": "Smoke Test Wedding",
            "event_type": "wedding",
            "closes_at": (now + timedelta(hours=6)).isoformat(),
            "reveal_at": (now + timedelta(hours=6)).isoformat(),
            "shot_limit": 3,
            "guest_cap": 2,
        },
    )
    check("film created", status == 201, f"status={status} {created}")
    if status != 201:
        return 1
    code = created["film"]["code"]
    host_token = created["host_token"]
    print(f"        code={code}  shot_limit=3  guest_cap=2")

    print("\nGuest joins with a name only, no account")
    status, joined = request("POST", f"{API}/v1/films/{code}/join", body={"display_name": "Ama"})
    check("guest joined", status == 201, f"status={status} {joined}")
    guest_token = joined["guest_token"]
    check("full roll available", joined["shots_remaining"] == 3, str(joined))

    print("\nReserve a slot, upload directly to storage, then commit")
    shot_id = str(uuid.uuid4())
    status, reserved = request(
        "POST", f"{API}/v1/films/{code}/shots/reserve",
        body={"shot_id": shot_id}, token=guest_token,
    )
    check("slot reserved", status == 200, f"status={status} {reserved}")
    check("counter decremented", reserved["shots_remaining"] == 2, str(reserved))

    put_status, _ = request(
        "PUT", reserved["upload_url"], raw=JPEG, content_type="image/jpeg"
    )
    check("bytes uploaded straight to storage", put_status == 200, f"status={put_status}")

    status, committed = request(
        "POST", f"{API}/v1/films/{code}/shots/{shot_id}/commit", token=guest_token
    )
    check("shot committed", status == 200 and committed["state"] == "uploaded", str(committed))

    print("\nIdempotency: replay the same shot id")
    status, replay = request(
        "POST", f"{API}/v1/films/{code}/shots/reserve",
        body={"shot_id": shot_id}, token=guest_token,
    )
    check("replay recognised, no slot burned",
          status == 200 and replay["already_reserved"] and replay["shots_remaining"] == 2,
          str(replay))

    print("\nThe reveal boundary")
    status, gallery = request("GET", f"{API}/v1/films/{code}/gallery")
    check("gallery reports it has not developed", gallery["is_developed"] is False, str(gallery))
    check("no photo URLs exist before reveal", gallery["photos"] == [], str(gallery))
    check("but the count is visible", gallery["shot_count"] == 1, str(gallery))

    raw_status, _ = request("GET", f"{STORAGE}/filmroll-shots/{reserved['storage_key']}")
    check("direct storage access denied", raw_status == 403, f"status={raw_status}")

    print("\nShot limit is enforced")
    for n in range(2):
        request("POST", f"{API}/v1/films/{code}/shots/reserve",
                body={"shot_id": str(uuid.uuid4())}, token=guest_token)
    status, over = request(
        "POST", f"{API}/v1/films/{code}/shots/reserve",
        body={"shot_id": str(uuid.uuid4())}, token=guest_token,
    )
    check("fourth shot on a 3-shot roll rejected", status == 409, f"status={status} {over}")

    print("\nGuest cap is enforced")
    request("POST", f"{API}/v1/films/{code}/join", body={"display_name": "Bem"})
    status, third = request("POST", f"{API}/v1/films/{code}/join", body={"display_name": "Cira"})
    check("third guest on a 2-guest cap rejected", status == 409, f"status={status} {third}")

    print("\nAuthorization")
    status, _ = request(
        "POST", f"{API}/v1/films/{code}/reveal", token=guest_token
    )
    check("guest cannot reveal the film", status == 403, f"status={status}")
    status, _ = request("POST", f"{API}/v1/films/{code}/reveal")
    check("anonymous cannot reveal the film", status == 401, f"status={status}")

    print("\nHost develops the film now")
    status, revealed = request("POST", f"{API}/v1/films/{code}/reveal", token=host_token)
    check("host revealed", status == 200 and revealed["is_developed"], str(revealed))

    status, gallery = request("GET", f"{API}/v1/films/{code}/gallery")
    check("gallery now developed", gallery["is_developed"] is True, str(gallery))
    check("photo present with attribution",
          len(gallery["photos"]) == 1 and gallery["photos"][0]["guest_name"] == "Ama",
          str(gallery))

    signed_status, blob = request("GET", gallery["photos"][0]["url"])
    check("signed URL serves the photo", signed_status == 200 and blob == JPEG,
          f"status={signed_status}")

    print("\nModeration")
    request("POST", f"{API}/v1/films/{code}/shots/{shot_id}/hide", token=host_token)
    status, gallery = request("GET", f"{API}/v1/films/{code}/gallery")
    check("hidden photo disappears from the gallery", gallery["photos"] == [], str(gallery))

    print(f"\n{passed} passed, {failed} failed\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
