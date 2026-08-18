#!/usr/bin/env python3
"""Wedding-scale burst against a running local stack.

Driven from the host rather than from inside the compose network, deliberately.
Presigned URLs are signed against the public endpoint a phone would use, and
SigV4 covers the Host header, so a client that rewrites the host gets
SignatureDoesNotMatch. Running here exercises the same path a real guest takes.

Scaled to 50 guests instead of the 150 a large wedding brings, because Docker
is allocated 8 GB on this machine and a full-size run pushes roughly 15 GB
through storage. Only the multiplier changed; the shape is identical.

Usage:  ./scripts/loadtest.sh     (wraps this with memory sampling)
        python3 scripts/loadtest.py
"""

from __future__ import annotations

import json
import pathlib
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

API = "http://localhost:8000"
PHOTO_PATH = pathlib.Path("/tmp/filmroll-loadtest.jpg")

GUESTS = 50
SHOTS_PER_GUEST = 20
WORKERS = 25
TOTAL = GUESTS * SHOTS_PER_GUEST

_lock = threading.Lock()
reserve_latencies: list[float] = []
statuses: list[int] = []


def record(status: int, latency: float | None = None) -> None:
    with _lock:
        statuses.append(status)
        if latency is not None:
            reserve_latencies.append(latency)


def call(
    method: str, url: str, *, body: object = None, token: str | None = None,
    raw: bytes | None = None, content_type: str | None = None,
) -> tuple[int, object]:
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    request = urllib.request.Request(url, data=data, method=method)
    if raw is None and body is not None:
        request.add_header("Content-Type", "application/json")
    if content_type:
        request.add_header("Content-Type", content_type)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read()
            try:
                return response.status, json.loads(payload)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return response.status, payload
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except Exception:
        return 599, None


def main() -> int:
    if not PHOTO_PATH.exists():
        print(f"error: {PHOTO_PATH} missing. Run ./scripts/loadtest.sh instead.", file=sys.stderr)
        return 1
    photo = PHOTO_PATH.read_bytes()
    total_mb = len(photo) * TOTAL / 1_000_000

    print(
        f"{GUESTS} guests x {SHOTS_PER_GUEST} shots = {TOTAL} photos, "
        f"{len(photo) / 1000:.0f} KB each, {total_mb:.0f} MB total"
    )

    now = datetime.now(UTC)
    status, created = call(
        "POST", f"{API}/v1/films",
        body={
            "title": "Load test wedding", "event_type": "wedding",
            "closes_at": (now + timedelta(hours=8)).isoformat(),
            "reveal_at": (now + timedelta(hours=8)).isoformat(),
            "shot_limit": SHOTS_PER_GUEST, "guest_cap": GUESTS,
        },
    )
    if status != 201:
        print(f"error: could not create film ({status})", file=sys.stderr)
        return 1
    code = created["film"]["code"]
    host_token = created["host_token"]
    status, checkout = call(
        "POST", f"{API}/v1/films/{code}/checkout",
        body={"tier_id": "g50"}, token=host_token,
    )
    if status != 200:
        print(f"error: could not entitle 50 guests ({status})", file=sys.stderr)
        return 1

    tokens: list[str] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for st, joined in pool.map(
            lambda n: call("POST", f"{API}/v1/films/{code}/join",
                           body={"display_name": f"Guest {n}"}),
            range(GUESTS),
        ):
            if st == 201:
                tokens.append(joined["guest_token"])
    if len(tokens) != GUESTS:
        print(f"error: only {len(tokens)}/{GUESTS} guests joined", file=sys.stderr)
        return 1

    def one_shot(index: int) -> None:
        token = tokens[index % GUESTS]
        shot_id = str(uuid.uuid4())

        start = time.perf_counter()
        st, reserved = call(
            "POST", f"{API}/v1/films/{code}/shots/reserve",
            body={"shot_id": shot_id}, token=token,
        )
        record(st, time.perf_counter() - start)
        if st != 200:
            return

        # Straight to object storage. These bytes never enter the API process,
        # which is what the memory sampling in loadtest.sh is there to prove.
        put_status, _ = call(
            "PUT", reserved["upload_url"], raw=photo, content_type="image/jpeg"
        )
        record(put_status)

        commit_status, _ = call(
            "POST", f"{API}/v1/films/{code}/shots/{shot_id}/commit", token=token
        )
        record(commit_status)

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(one_shot, range(TOTAL)))
    elapsed = time.perf_counter() - started

    ordered = sorted(reserve_latencies)
    p50 = statistics.median(ordered)
    p95 = ordered[int(len(ordered) * 0.95) - 1]
    p99 = ordered[int(len(ordered) * 0.99) - 1]
    server_errors = [s for s in statuses if s >= 500]
    ok = statuses.count(200)

    print()
    print(f"film             {code}")
    print(f"elapsed          {elapsed:.1f}s  ({TOTAL / elapsed:.0f} photos/s)")
    print(f"reserve latency  p50 {p50 * 1000:.0f}ms  p95 {p95 * 1000:.0f}ms  p99 {p99 * 1000:.0f}ms")
    print(f"requests         {len(statuses)} total, {ok} ok, {len(server_errors)} 5xx")
    print(f"to storage       {total_mb / elapsed:.1f} MB/s")

    failures = []
    if server_errors:
        failures.append(f"{len(server_errors)} server errors")
    if ok < TOTAL * 3:
        failures.append(f"only {ok} of {TOTAL * 3} requests succeeded")
    if p95 >= 1.0:
        failures.append(f"p95 reserve latency {p95 * 1000:.0f}ms exceeds 1000ms")

    print()
    if failures:
        for failure in failures:
            print(f"FAIL  {failure}")
        return 1
    print("PASS  no server errors, every request succeeded, p95 within budget")
    return 0


if __name__ == "__main__":
    sys.exit(main())
