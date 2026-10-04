# Continue — API surface

Canonical plan: parent `ROADMAP.md`. Do not replace it.

**Shipped:** films/guests/shots, reserve/commit, reveal gating, hide, host review, QR/PDF, ZIP on media worker, Stripe Checkout + entitlements, receipts/refunds/VAT, co-host/photographer seats, host magic-link recover, reveal + retention email, AASA placeholder.

**Phase 2 leftovers that need API:** chunked/resumable upload (only if web needs it). Do not add it speculatively.

**Phase 3 leftovers:** none on this API. Guest reveal push ships with `PUT /v1/films/{code}/push-token` and the existing `notify_developed_films` job. Instant films still skip it. Empty `EXPO_PUSH_URL` captures messages in `app.services.push.outbox`. Do not send from a URL the client supplied — tokens are validated as `ExpoPushToken[…]` first.

`shared_gallery` (default true) is who sees whom after develop, not a second reveal. Private galleries still develop on schedule; `GET /gallery` mints URLs only when an optional guest bearer matches the shot's guest. A host token must return empty photos — the inbox is how staff see the whole roll. Unlike `instant_reveal` this field is on `FilmUpdate`.

Instant reveal (`Film.instant_reveal`) is a creation-only flag. Do not add a PATCH to turn it off: once guests have seen a photo it cannot be un-seen. Implementation reuses `_IS_DEVELOPED` by stamping both `reveal_at` and `revealed_at` at create — `reveal_at` alone races the database clock, and the create response would come back undeveloped. Do not grow a second gallery predicate. `notify_developed_films` already skips live films. Hide still applies.

Reports (`app/services/reports.py`) are guest-scoped and deduped by a `(shot_id, guest_id)` unique constraint via `ON CONFLICT DO NOTHING`, so a retry on a venue's bad wifi cannot inflate the count. A report never hides a shot and must not grow an auto-hide threshold — the `ShotReport` docstring says why. The host inbox gets the count but never the reporter's name or reason; do not add either to `ReviewPhoto`.

**Test isolation:** patch settings with `monkeypatch.setattr(get_settings(), "field", value)`. Never `setenv` + `get_settings.cache_clear()` — the cache is cleared before monkeypatch restores the env, so the overridden value gets re-cached for the rest of the session and breaks unrelated tests.

The join PIN lives in `app/services/pins.py` and is an HMAC under `SECRET_KEY`, never bcrypt — the module docstring has the threat model, read it before "upgrading" the hash. Two rules that are easy to break: the PIN is checked *after* the rate limiter in `join`, so a wrong guess spends one of the caller's 20 hourly attempts, and it gates joining only. An existing guest token already proves the guest got in, so adding a PIN mid-event must never lock out someone already holding a camera.

Deletion is two-stage. `soft_delete` sets `deleted_at` and every read path already filters on it, so the film 404s at once; `load_by_code(..., include_deleted=True)` exists for restore alone. The hourly `purge_deleted_films` task erases the S3 prefix, shots, and guests once `deleted_at` is older than `DELETED_FILM_GRACE_DAYS`, then stamps `purged_at`. Do not hard-delete the `films` row — payments cascade off it, and after `purged_at` restore must return 410 rather than a resurrected film with no photos. Restore is the only route using `BearerPrincipal`, and it answers 404 (never 403) so a wrong token cannot confirm that a deleted film exists.

Authorisation has three staff dependencies, not one. `require_host_owner` is the film creator alone (seats, payments, host account); `require_host` adds co-hosts (moderate, reveal, PATCH, checkout); `require_film_staff` adds the photographer (review, export). A seat token carries the seat id in `sub` and the row is re-read on every request, which is what makes revocation immediate. Never widen a route by swapping in `require_film_staff` without deciding whether a photographer should hold that power.

**Guest clips (Phase 6) + video pack (Phase 4):** `Film.video_pack` is granted by the `video_pack` add-on. `Shot.kind` is `photo` or `clip`; each kind has its own reserve SQL and per-guest count, so a clip never spends a photo and `unlimited_shots` never lifts the clip cap. Clips use `max_clip_bytes` / `allowed_clip_types` at commit, and commit enqueues `transcode_clip` (media queue — only that image has ffmpeg) instead of `generate_derivatives`. The original is never served: `_IS_PLAYABLE` keeps a clip out of gallery, review and export until `derivative_at` is set, and `_media()` presigns `storage.clip_key` / `poster_key`. The ZIP writes the transcode as `.mp4`. Run the transcode test in the media image: `docker compose run --rm worker-media pytest tests/test_clips.py`.

Billing rules that already hold: a refund records `refunded_cents` and never lowers `entitled_guest_cap` (a live film has already seated those guests, and the check constraint would reject it). Partial refunds keep `status="paid"`. `GET /v1/films/{code}/payments` is host-only and hides abandoned `open` sessions. Tax comes from the webhook body, never recomputed.

**Phase 5:** AASA is already served. Do not build an App Clip in this repo. Keep `APPLE_TEAM_ID` / bundle ids in settings.

If the user says continue in `backend/`, extend `/v1` for the **current** client slice. Do not invent a second upload protocol.
