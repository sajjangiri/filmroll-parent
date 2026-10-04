---
name: filmroll-continue
description: Filmroll product plan memory — current phase, what is already shipped, and what to build next without restarting the Once-clone roadmap. Use when continuing Filmroll work, choosing the next slice, or when the user says continue.
---

# Continue Filmroll from the existing plan

Do **not** rewrite `ROADMAP.md` or start a new architecture. Clone the Once loop, then add what Once is missing. First public launch is Phases 1–4 (already the sellable web product). Phase 5 is an iPhone acquisition upgrade, not a revenue prerequisite.

## Where we are (2026-09-27)

| Phase | Status | Notes |
|---|---|---|
| 0 Prototype | DONE | JSON/`public/uploads` debt cleared in Phase 1 |
| 1 Foundation | DONE | Postgres, MinIO, signed uploads, idempotent shot ids |
| 2 PWA guest | DONE | Offline queue, torch, zoom, resumable PUT, WebGL preview, i18n EN/ES/FR, a11y pass |
| 3 Host tools | DONE | Inbox, hide, PDF cards, ZIP, seats, delete + restore, join PIN, report a photo, instant-reveal, private vs shared, reveal email + guest push. Leftover: none on web; clip ephemeral is Phase 5 |
| 4 Money | DONE | Web Checkout, entitlements, receipts/refunds/VAT, video pack add-on. StoreKit stays Phase 5 |
| 5 Native iOS | IN PROGRESS | Expo create + host dashboard + guest camera + offline queue + AASA shipped; mobile host tools at web parity except billing. **Do not start the App Clip.** Next: App Store binary — **blocked on the user**: Apple signing team and a public https API/web/storage host (both deferred 2026-09-27). Release config (`buildNumber`, export compliance) is in `app.json`; see `mobile/README.md` → Release build |
| 6 Android + moat | IN PROGRESS | Android host app, guest video clips, and live slideshow done. Next in order: recap video |

Last slice: Phase 6 live slideshow. `/f/{code}/slideshow` is a full-screen venue wall that polls the public gallery (no token, so hide and the reveal gate carry over). Newest shots nobody has seen yet go up first; then the roll cycles. Photos use `display_url` (1280 px webp); clips play muted and advance on `ended`. Space pauses (and pauses a clip); right arrow skips. Wake Lock keeps a projector laptop awake. A private film shows the join QR and no photos. Opened from the web host dashboard and mobile host Settings.

Before that: Phase 6 guest video clips + Phase 4 video pack. `video_pack` add-on ($19) unlocks `CLIPS_PER_GUEST` (3) clips of up to `CLIP_MAX_SECONDS` (15), a separate allowance from the photo roll (`shots.kind`). Reserve with `kind: "clip"`; commit enqueues `transcode_clip` on the `media` queue (ffmpeg: trim, ≤1280 px, H.264/AAC, metadata stripped, poster webp). Gallery/review/ZIP only include a clip once transcoded (`derivative_at`), and only ever serve the transcode. Web records with MediaRecorder; the Expo app with `expo-camera` `recordAsync` and plays with `expo-video`. The mic permission is requested only on first record (Android `RECORD_AUDIO` is no longer blocked). The transcode test needs ffmpeg: `docker compose run --rm worker-media pytest tests/test_clips.py`.

Before that: Phase 6 Android host app — same Expo app on Android, `/.well-known/assetlinks.json` (`ANDROID_CERT_SHA256`), `GET /v1/films/{code}/qr.png` for native. Found and fixed a camera bug that hit iOS too (Hermes has no `crypto.randomUUID`; see mobile `continue.md`).

Before that, mobile (2026-09-27): the Once-style three-step host flow (Create → Film ready/Invite → Capture as host, film home with Photos / Invite / Settings tabs), then delete + restore, then seats (owner invites/removes co-host or photographer; the app claims `?seat=` invite links and renders by role). Details in `mobile/.cursor/skills/filmroll-mobile/continue.md`.

Before that: join PIN on the mobile host screen. Guests already typed it on join; the host who created the film from the phone can now require, change, or remove it without opening the web dashboard. Same `PUT`/`DELETE /v1/films/{code}/pin` as web. Adding a PIN mid-event never locks out someone already holding a camera.

Before that: reveal push. Hosts already get email; guests who joined from the app register an Expo token (`PUT /v1/films/{code}/push-token`) and the same `notify_developed_films` job fans it out. Instant films still skip the notice. Empty `EXPO_PUSH_URL` captures messages in `app.services.push.outbox` like mail. Expo Go on SDK 57 often cannot mint a remote token — a development or App Store build is what actually delivers. Ephemeral clip notifications stay Phase 5.

Before that: private vs shared gallery. Default is a shared album. `shared_gallery=false` mints gallery URLs only for the calling guest; the host inbox and ZIP still hold the whole roll. Unlike instant-reveal this can be PATCHed later. `GET /gallery` takes an optional guest bearer — a host token must not unlock other people's photos. Shipped on **web + mobile** create forms, guest galleries (pass the guest token), and host dashboards.

Before that: instant-reveal (live gallery). `instant_reveal` on create stamps `reveal_at` to now so the existing SQL reveal predicate is already true — no second way for a photo to become visible. Hide still works. The flag is creation-only because guests cannot un-see a shot. Shipped on **web + mobile** create forms; mobile `FilmScreen` shows camera *and* gallery on a live film (it used to treat `is_developed` as "gallery only", which would have made live films unshootable).

Before that: guests reporting a photo. `POST /v1/films/{code}/shots/{shot_id}/report` (guest token, one per guest per shot), `report_count` per photo and `reported_count` on the host inbox. A report **never hides anything** — see the `ShotReport` docstring before adding an auto-hide threshold. Shipped on web + mobile guest galleries.

Before that: the optional join PIN. `PUT`/`DELETE /v1/films/{code}/pin` (host or co-host), `requires_pin` on `FilmPublic`, `join_pin` on the join request. Stored as an HMAC under `SECRET_KEY` — see `app/services/pins.py` for why that beats bcrypt here. Shipped on **all three surfaces**: web guest + host, mobile guest.

Before that: deleting a film. `DELETE /v1/films/{code}` (owner only) sets `deleted_at` so everything 404s immediately, but the objects live for `DELETED_FILM_GRACE_DAYS` (30) so a mistap is recoverable via `POST /{code}/restore`. The hourly `purge_deleted_films` beat task then erases objects/shots/guests and stamps `purged_at`, keeping the film row so payment records survive.

Before that: co-host and photographer seats. Access beyond the film creator is a revocable `film_seats` row that the JWT points at, re-read on every request. `host` (creator) manages seats and money, `cohost` moderates and reveals, `photographer` reads the inbox and pulls the ZIP. Both slices now ship on web and mobile.

## Forced order (never skip)

```
Web PWA → native iOS App Store binary → App Clip from QR → Android host (optional)
```

An App Clip cannot ship without a published full iOS app. QR clips are capped at 15 MB uncompressed. Same URL on Android must keep opening the PWA.

## If the user says "continue"

Pick the next **unchecked** box in `ROADMAP.md` for the phase they are in. Default if unspecified:

1. Do not rebuild Phases 0–1.
2. Do not start SwiftUI/App Clip/StoreKit.
3. Reasonable next slices (any one, not all):
   - Phase 3 leftovers on **mobile**: none (seats + delete/restore shipped)
   - Phase 5 on **mobile**: the App Store binary, once the user gives a signing team and production URLs. Universal links also need the live domain. Do not start the App Clip or StoreKit.
   - Phase 6 in ROADMAP order (the user asked for sequential): Android done → guest video clips done → live slideshow done → recap video → multiple rolls → photobook → brand pack → white-label.

Phase 4 is done (the video pack shipped with guest clips).

## Invariants that survive every slice

- Photo bytes never transit Next.js or FastAPI; clients PUT to storage.
- Reveal is SQL: `revealed_at IS NOT NULL OR now() >= reveal_at` (database clock).
- Caps use `SELECT … FOR UPDATE` (guest row for shots, film row for joins).
- Client-generated shot UUIDs.
- Celery only `after_commit`. Queues `fast` vs `media`.
- Charge for capacity, never per shutter. Billing is web-first.
- `guest_cap <= entitled_guest_cap` is a DB check.
- No accounts anywhere. Extra access is a revocable seat row, never a login.
- Deletion hides immediately and erases after a grace window. Never hard-delete a film row: payments cascade off it and receipts are tax records.

Full lists: `ROADMAP.md`, `FEATURES.md`.
