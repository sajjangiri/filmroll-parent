---
name: filmroll-continue
description: Filmroll product plan memory — current phase, what is already shipped, and what to build next without restarting the Once-clone roadmap. Use when continuing Filmroll work, choosing the next slice, or when the user says continue.
---

# Continue Filmroll from the existing plan

Do **not** rewrite `ROADMAP.md` or start a new architecture. Clone the Once loop, then add what Once is missing. First public launch is Phases 1–4 (already the sellable web product). Phase 5 is an iPhone acquisition upgrade, not a revenue prerequisite.

## Where we are (2026-10-05)

| Phase | Status | Notes |
|---|---|---|
| 0 Prototype | DONE | JSON/`public/uploads` debt cleared in Phase 1 |
| 1 Foundation | DONE | Postgres, MinIO, signed uploads, idempotent shot ids |
| 2 PWA guest | DONE | Offline queue, torch, zoom, resumable PUT, WebGL preview, i18n EN/ES/FR, a11y pass |
| 3 Host tools | DONE | Inbox, hide, PDF cards, ZIP, seats, delete + restore, join PIN, report a photo, instant-reveal, private vs shared, reveal email + guest push, guest save a photo (web share sheet / download, mobile expo-sharing). Leftover: none; clip ephemeral is Phase 5 |
| 4 Money | DONE, one item open | Web Checkout, entitlements, receipts/refunds/VAT, video pack add-on. StoreKit stays Phase 5. **Open (2026-10-05): local payment methods for Nepal**; Stripe does not onboard Nepal businesses. Design first, then merchant accounts and NPR prices from the user |
| 5 Native iOS | IN PROGRESS | Expo create + host dashboard + guest camera + offline queue + AASA shipped; mobile host tools at web parity except billing. **Do not start the App Clip.** Next: App Store binary — **blocked on the user**: Apple signing team and a public https API/web/storage host (both deferred 2026-09-27). Release config (`buildNumber`, export compliance) is in `app.json`; see `mobile/README.md` → Release build |
| 6 Android + moat | IN PROGRESS | Android host app, guest video clips, live slideshow, hearts and camera-roll upload done. **Recap video paused by the user (2026-10-04)**: focus is the Once-style photo loop. Multiple rolls needs a design and the user's go-ahead |

Last slice (2026-10-05): **camera-roll upload**, chosen by the user from three options (Once lacks it, and a US App Store review of Once calls it the app's "ONE massive flaw"; POV has it). `films.camera_roll` (host toggle, off by default, on create and PATCH) and `shots.source` (`camera` / `library`), migration `3c8f1e6a9b27`. A pick spends a shot from the same roll through the same reserve SQL. `films.ensure_accepting` is the window rule: the camera stops at close, a camera-roll photo is accepted until the album opens (a live film: only while open). Turning the toggle off answers 409, never 403, because both clients read a 403 on upload as a dead guest token. Clients re-encode every pick before it is queued (web: canvas in `web/lib/camera-roll.ts`; app: `expo-image-manipulator` in `mobile/src/camera-roll.ts`), so the original in the host's ZIP carries no EXIF or GPS, HEIC never reaches the worker, and the longest edge is at most 4096 px. The photo's own EXIF date (with `OffsetTimeOriginal` when present) feeds the date stamp, and the API accepts any date after 2000 for `library`. Guests get "Add photos from your phone" on the roll screen and on the developing screen; hosts get the toggle in the create flow and Settings, and a "From phone" / "Phone" badge in the inbox. Verified on web (390 px) and the Android emulator, including the stripped originals and the stamp dates; **not yet on iOS**, which needs a rebuild for the two new native modules.

Pricing check (2026-10-05): the "level with Once" note holds. Once's own calculator (once.film/pricing, values in the page source) and its US App Store list 10 for $1.99, 25 for $4.99, 50 for $14.99, 100 for $29.99, 150 for $49.99, 200 for $69.99, unlimited for $99.99, and unlimited shots for $9.99. The $14.99 / $59.99 figures came from another storefront: the App Store shows only about ten in-app purchases per country, at different price points. Real gaps the user may act on: Once includes storage with no time limit (we sell keep-forever for $14.99 after 12 months) and has an unlimited-guest tier. The user said they will revise pricing later, after more product work, and that Filmroll has to work in Nepal, which needs local payment methods (Phase 4, open).

Before that (2026-10-05), the two Once features we lacked, chosen by the user after a Once comparison (Once's own release notes: "Hosts can update camera styles before films end", "Hosts can remove participants directly from their films"; Once advertises no multiple rolls, camera-roll upload, templates or likes):
- **Remove a guest.** `GET /v1/films/{code}/guests`, `DELETE /v1/films/{code}/guests/{id}?hide_photos=` (host and co-host). `guests.removed_at`; the cap and `guest_count` count active guests only; guest tokens are now re-checked against the row on every request (`require_guest`, `optional_guest`) and a removed one gets 403 `"removed from this film"`, which web and app turn into a remembered "The host removed you" screen instead of a fresh join form. Their photos are hidden by default (ordinary per-photo hide, reversible); their push token is deleted.
- **Camera styles.** `films.look` in `warm` / `faded` / `mono` (`app.services.look.STYLES`). `FilmPublic.look_params` carries the constants to the web shader, so the viewfinder cannot drift from the develop step. Changing the style is refused once the album is open (409) and otherwise queues `redevelop_film`. The app has no live shader, so its camera says "Develops in black and white" / "Develops faded" under the title.


Before that (2026-10-05): **hearts** in the album on web and both apps. `PUT`/`DELETE /v1/films/{code}/shots/{id}/heart` (guest token, idempotent both ways, `shot_hearts` with one row per guest per shot). Only a photo the guest can see in their album can be hearted: developed film, not hidden, developed copy ready, and their own shots on a private film; everything else is a 404 so a heart never confirms a hidden photo exists. The gallery returns `heart_count` and `hearted`; the host inbox returns `heart_count`. Guests get a heart button in the photo viewer, a count on tiles (top corner, clear of the date stamp) and an "All / Most loved" switch once anything is loved. Multiple rolls (next in Phase 6) still waits for the user's go-ahead because it changes the product model.

Before that (2026-10-05): the **event-day dashboard** (FEATURES §7, the last open Phase 1 item). `GET /v1/ops/summary` behind a new `OPS_TOKEN` (empty = off), shown at `/ops` on the web: join and upload funnel for 15 min / 1 h / 24 h, the develop backlog (stuck vs never developed, aligned with the straggler job), Celery queue depth, stack health, and every open or busy film. No new infrastructure; two indexes added concurrently. Its first run on the dev database surfaced three photos from August and September that never developed. To use it, set `OPS_TOKEN` in `.env` and restart the API.

Before that (2026-10-04): the film look is now developed server-side. The worker renders the viewfinder's look (`backend/app/services/look.py`, a port of the WebGL shader) into an EXIF-free full-size JPEG and a 1280 px WebP, fixes EXIF rotation, and prints an optional date stamp (`Film.date_stamp`, toggled from create forms and settings; a toggle re-renders the roll). The public gallery never serves originals again; the staff inbox and ZIP still do. `make redevelop` re-renders after a look change.

**Redesign status (second session, 2026-10-04): built and verified on every surface, waiting on the user's review.** Web guest and host were checked in headless Chrome at 390 px and 1280 px; the app's guest and host flows were driven on the Android 15 emulator against the :8001 verification API (join, camera, roll, developing, album, viewer; home, new film, film ready, film home with all three tabs, including real hide, save, PIN, seat invite and develop calls). The venue slideshow and the print page are restyled too (checked at 1920×1080 and 1366×768, and as an A4 PDF). Fixed along the way: the Android keyboard covering the join name field, two dashboards overwriting a half-typed cap or shot limit on their 8 s refresh, the host "shots" count leaving hidden shots out, guest roll lines that went stale after close and develop, and the slideshow printing seconds in the develop time. Then (same day, "continue the plan"): **Extend and Change develop time** are built on both dashboards with a conservative rule the user can still overrule. Extend adds 1/2/4 hours (from now if the camera already closed, labelled "Reopen"); a film that develops when it closes keeps doing so; an extension that would cross a fixed develop time is disabled with the reason, because shots after the develop time skip the dark. Change offers "When the camera closes" and "Next morning at 10:00" (plus a custom time on web, never before the close). The rule lives in `web/lib/timing.ts`, mirrored in `mobile/src/timing.ts`. **iOS** rebuilt cleanly on Xcode 27 with the new native packages (the old `RuntimeScheduler.h` hand patch was not needed); Home, Film home, join card, roll and developing were checked on the iPhone 17 Pro simulator by deep link. The rest of the iOS tap-through was left to the user, who was testing on the same simulator at the time. Fixed: opening one film's link from inside another film kept the first film's guest token and roll (screens are now keyed by film code in `App.tsx`). Verification recipe: the mobile and web continue notes.

Next, already agreed with the user: a Once-inspired redesign of all four flows (web guest, mobile guest, web host, mobile host), "warm film" look (ink `#100e0c`, paper `#ece6dc`, accent `#ff8a2a`, Instrument Serif). The clickable prototype is the private Design artifact https://claude.ai/artifact/H5Ej3R5Hy6pDNeCYCCrJ9u. Build only after the user signs off on it; keep `/f/{code}` stable; borrow Once's patterns, never its copy. Pricing was decided 2026-10-04 (the user delegated it): level with Once at 25/50/100 guests and cheaper for big weddings; the ladder lives in `backend/app/services/catalog.py`. Web guests get an "Add to calendar" (.ics, built client-side) on the developing screen; app guests get the reveal push instead. Secondary text colour is `#9a9187` (4.5:1 on ink and on cards). Don't commit; the user handles git across the nested repos.

Before that: closed Phase 3 for real with guest "save a photo" on web and mobile. It saves `photo.url` (exactly what the tile shows) through the system share sheet, never a photo-library permission, which is also how the App Clip will have to do it. The production bucket needs CORS GET for the web origin (`backend/README.md`).

Before that: Phase 6 live slideshow. `/f/{code}/slideshow` is a full-screen venue wall that polls the public gallery (no token, so hide and the reveal gate carry over). Newest shots nobody has seen yet go up first; then the roll cycles. Photos use `display_url` (1280 px webp); clips play muted and advance on `ended`. Space pauses (and pauses a clip); right arrow skips. Wake Lock keeps a projector laptop awake. A private film shows the join QR and no photos. Opened from the web host dashboard and mobile host Settings.

Before that: Phase 6 guest video clips + Phase 4 video pack. `video_pack` add-on ($9.99) unlocks `CLIPS_PER_GUEST` (3) clips of up to `CLIP_MAX_SECONDS` (15), a separate allowance from the photo roll (`shots.kind`). Reserve with `kind: "clip"`; commit enqueues `transcode_clip` on the `media` queue (ffmpeg: trim, ≤1280 px, H.264/AAC, metadata stripped, poster webp). Gallery/review/ZIP only include a clip once transcoded (`derivative_at`), and only ever serve the transcode. Web records with MediaRecorder; the Expo app with `expo-camera` `recordAsync` and plays with `expo-video`. The mic permission is requested only on first record (Android `RECORD_AUDIO` is no longer blocked). The transcode test needs ffmpeg: `docker compose run --rm worker-media pytest tests/test_clips.py`.

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
   - Phase 6 in ROADMAP order (the user asked for sequential): Android done → guest video clips done → live slideshow done → recap video (paused) → hearts done → camera-roll upload done → multiple rolls (design first) → photobook → brand pack → white-label.

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
