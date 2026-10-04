# Continue — mobile surface

Canonical plan: parent Filmroll `ROADMAP.md`. Do not replace it.

**Shipped here (Phase 5):** create film, host dashboard (inbox hide/unhide, develop now, export ZIP, cap edits, recovery email), join by code, native camera, gallery, offline queue, guest i18n EN/ES/FR, a11y pass (44pt targets, `accessibilityState`, `announceForAccessibility` after each shot), custom scheme + universal link routing (`/f/{code}` guest, `/f/{code}/host` host), AASA is **backend**.

Host flow mirrors Once's three steps: `CreateFilmScreen` (name, your name, hours; the rest behind "More options") → `FilmReadyScreen` (QR + "Share invite") → the camera. "Start shooting" and the film home's "Take photos" open `FilmScreen joinAsHost`, which auto-joins with the name saved by `saveHostName` (falls back to the form on PIN films). The host's camera takes a guest seat. `HostScreen` is the film home: Photos / Invite / Settings tabs; without a host key it shows only Invite + recovery.

The guest join form handles the optional PIN: `FilmPublic.requires_pin` decides whether the field is shown, and `joinFilm(code, name, pin)` sends it. A wrong PIN is a 403, distinct from 409 full and 410 closed.

The gallery in `FilmScreen` lets a guest report a photo, gated on holding a guest token. It is optimistic and announces via `announceForAccessibility`; a failure rolls the local state back.

Instant-reveal films are born `is_developed`. `FilmScreen` must keep showing the camera while the film is open — `is_developed` is not "gallery only". Poll the gallery every 8s when `instant_reveal` is set.

Private films (`shared_gallery: false`) only mint gallery URLs for the calling guest. `getGallery(code, token)` must pass the guest token loaded from storage (and the token just returned from join). The host inbox is still the whole roll.

After join, `registerGuestPush` asks for notification permission and `PUT`s an Expo token. Instant films skip the ask. Failures are silent: Expo Go often cannot mint a remote token, and joining still has to work. Tapping the notification opens the guest film via `data.code`.

Delete + restore live at the bottom of the Settings tab (type the code to confirm). Like web, the deleting phone stashes `FilmDeleted` under `filmroll-deleted-{code}` because a deleted film is a 404 to everyone; `HostScreen` shows "Film deleted" + Restore from that note until `purge_at`.

Seats: the owner invites a co-host or photographer from Settings → People (`createSeat`, share the one-time `invite_url`, `revokeSeat`). Opening `/f/{code}/host?seat=…` in the app (`parseFilmrollUrl` → `seat`) calls `claimSeat`, stores the seat token as the host token and the role under `filmroll-role-{code}`. `HostScreen` renders by role like web: owner-only = recovery email, People, Delete (and it never requests `host/account` or `seats` otherwise, both 403); photographer = inbox read + export only. A magic link always restores the owner role.

**Android (Phase 6, first item):** the same Expo app builds and runs on an Android 15 emulator; the whole host + guest loop was verified there including a real upload. Fixes that came out of it apply to iOS too: shot ids use `newShotId()` (Hermes has no global `crypto`, so every shot used to fail before it hit disk), QR loads `qr.png` (RN `Image` cannot draw SVG), safe areas via `react-native-safe-area-context`, push registration runs once per guest token (it re-prompted on every film refresh), and the camera preview caps at half the window height so the shutter stays visible on 16:9 phones. System Back is handled in `App.tsx`. App Links: `intentFilters` in `app.json` + backend `/.well-known/assetlinks.json` (`ANDROID_CERT_SHA256`).

**Parity with web host tools:** done on mobile except billing (Stripe stays on web by design). The join PIN can be set and cleared from `HostScreen`; guests already type it on join.

The PIN is digits only (4–8). Adding one mid-event never locks out a guest who already holds a camera.

**Guest clips:** with the film's video pack (bought on the web), `CameraScreen` shows a Photo / Clip switch; clip mode sets `CameraView mode="video"` and calls `recordAsync({ maxDuration })`. The microphone is requested from the record button only (`useMicrophonePermissions({ request: false })`), so photo-only guests never see that prompt; `app.json` therefore no longer blocks `RECORD_AUDIO`. Queue rows carry `kind` and keep the file extension, which is how `clipContentType` knows iOS `.mov` from Android `.mp4`. `ClipTile` shows the poster and opens an `expo-video` player in a modal, so a long gallery never holds dozens of players. `expo-video` is native: rebuild both platforms after pulling, and re-check the `RuntimeScheduler.h` patch after any install.

**Saving a photo:** the gallery footer has Save beside Report. `shareMedia` (`src/share-media.ts`) downloads `photo.url` into the cache and hands it to `expo-sharing`, so iOS offers "Save Image" and Android its targets, with no photo-library permission. That is also the only route an App Clip will have. RN `Share` cannot send a file on Android. `expo-sharing` is native: rebuild both platforms after pulling. Errors in the gallery render under the section title, since the join form (which used to own `error`) is gone once a guest has joined.

**Venue slideshow:** the wall itself is a web page. Settings → Open slideshow launches `${WEB_URL}/f/{code}/slideshow` when the gallery is shared; a private film explains why the wall is off.

**Next (still this app, not an App Clip):**

- Physical-device `EXPO_PUBLIC_API_URL` / universal links once the domain is live
- StoreKit 2 IAP for paid tiers (web Stripe remains for margin until then)
- Then a **published App Store binary** — hard prerequisite
- Only after that: App Clip ≤15 MB (separate native target, not this Expo tree)

**Do not start:** App Clip, StoreKit 2.

**Also on web (not instead of mobile):** Stripe Checkout for paid tiers (margin decision — web ~97% vs Apple 15–30%).
