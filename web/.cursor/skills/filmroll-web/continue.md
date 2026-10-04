# Continue — web surface

Canonical plan: parent `ROADMAP.md` / `FEATURES.md`. Do not replace it.

**Shipped here:** guest PWA camera, offline queue, host create/dashboard/inbox/hide, print cards, ZIP trigger, Stripe Checkout UI, host email recover, co-host and photographer seats.

`HostDashboard` renders against a role, not a boolean. `loadStaffRole(code)` returns `host` / `cohost` / `photographer`, defaulting to `host` for devices that predate seats. Gate owner-only UI (receipts, room size, recovery email, the People section) on `isOwner` and mutating UI on `canWrite`; the API enforces the same split, so a mistake here leaks layout, not data. `/f/{code}/host?seat=…` is claimed on load and the invite is stripped from the URL.

**Phase 2 is closed.** Resumable upload, WebGL look preview, torch/zoom, i18n EN/ES/FR, and the a11y pass all shipped. Do not reopen it without a bug.

A11y rules that must hold: 44px minimum tap targets, `:focus-visible` rings from `globals.css` (`.on-preview` for controls over the camera), `role="alert"` on errors, a polite live region confirming each shot, and error state stored as a `MessageKey` so a language switch retranslates it.

**Phase 4 leftovers:** none on this surface. Receipts, refunds, and tax lines ship in `HostDashboard` off `GET /v1/films/{code}/payments`. The video pack is bought here and used on the guest camera.

`shared_gallery` is on create and on PATCH. The guest gallery must pass `loadGuestToken(code)` into `getGallery` or a private film looks empty even to the person who shot it. A host token must not be sent — the API treats non-guest bearers as anonymous, which is how the inbox stays the only full view.

**Phase 5:** Smart App Banner only after a real App Store id. Same `/f/{code}` URL must keep working as the Android fallback.

**Not this repo:** Expo camera, FastAPI internals, App Clip binary.

Deleting a film puts the dashboard in a state no fetch can describe: the film 404s for its own owner too. `saveDeleted(code, …)` stashes the restore deadline so a reload still offers a way back, and `refresh` treats a 404 with that key present as "deleted" rather than "not found". Restore is therefore device-local by design, matching the no-accounts model.

The gallery is public but reporting is not: the report control renders only when `loadGuestToken(code)` returns something, so a link-holder who never joined cannot flag photos. The host inbox floats reported-and-still-visible shots to the top and rings them amber, because that is the only thing in the inbox actually waiting on a decision.

If the user says continue and is in `web/`, Phase 3 leftovers on this surface are done. Guest "save a photo" is the remaining Phase 3 P1 in `FEATURES.md` if they stay here; otherwise mobile host parity (seats, delete, PIN).

Guest clips: when `film.video_pack` is set, `Camera` shows a Photo / Clip switch. Clip mode records the **raw** camera track plus a microphone stream requested on first record (never with the camera), auto-stopping at `film.clip_max_seconds`. A video blob goes through the same IndexedDB queue; `captureShot` reserves it as `kind: "clip"` and PUTs with the `content_type` the reserve response echoes (browsers append codec parameters the signature would not match). `ClipTile` pins the first signed URL so the 8 s gallery poll does not restart playback. The host buys the pack from the dashboard's add-on list.

Venue slideshow: `/f/{code}/slideshow` is the public gallery on a loop, not a second feed. It never sends a token, so a private film and an undeveloped film show the join QR instead of photos. Newest unseen shots go first so a photo taken on the dance floor hits the wall within one poll. Photos use `display_url` (the 1280 px derivative); clips play muted and hold the slide until they end. Space pauses, including the clip; right arrow skips. `HostDashboard` opens it in a new tab.
