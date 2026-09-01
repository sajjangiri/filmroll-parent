---
name: filmroll-continue
description: Filmroll product plan memory — current phase, what is already shipped, and what to build next without restarting the Once-clone roadmap. Use when continuing Filmroll work, choosing the next slice, or when the user says continue.
---

# Continue Filmroll from the existing plan

Do **not** rewrite `ROADMAP.md` or start a new architecture. Clone the Once loop, then add what Once is missing. First public launch is Phases 1–4 (already the sellable web product). Phase 5 is an iPhone acquisition upgrade, not a revenue prerequisite.

## Where we are (2026-09-01)

| Phase | Status | Notes |
|---|---|---|
| 0 Prototype | DONE | JSON/`public/uploads` debt cleared in Phase 1 |
| 1 Foundation | DONE | Postgres, MinIO, signed uploads, idempotent shot ids |
| 2 PWA guest | IN PROGRESS | Offline queue shipped; leftover: chunked upload, WebGL look, torch/zoom, i18n, a11y |
| 3 Host tools | DONE | Inbox, hide, PDF cards, ZIP. Leftover: co-hosts, photographer seat, PIN |
| 4 Money | IN PROGRESS | Web Checkout + entitlements shipped. Leftover: video pack, receipts/VAT |
| 5 Native iOS | IN PROGRESS | Expo guest camera + offline queue + AASA shipped. **Do not start the App Clip.** Next: App Store binary, then clip ≤15 MB |
| 6 Android + moat | P2 | Not started |

Last product slice: native shutter writes the JPEG to disk first, then drains the same reserve → PUT → commit path as the PWA.

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
   - Phase 2 leftovers on **web** (chunked upload, torch, WebGL preview that is never baked into the original)
   - Phase 4 leftovers (VAT/receipts, video pack) on **web + api**
   - Phase 5 polish on **mobile** (LAN / universal links) — still guests only. Offline queue is shipped. Do not start the App Clip.

## Invariants that survive every slice

- Photo bytes never transit Next.js or FastAPI; clients PUT to storage.
- Reveal is SQL: `revealed_at IS NOT NULL OR now() >= reveal_at` (database clock).
- Caps use `SELECT … FOR UPDATE` (guest row for shots, film row for joins).
- Client-generated shot UUIDs.
- Celery only `after_commit`. Queues `fast` vs `media`.
- Charge for capacity, never per shutter. Billing is web-first.
- `guest_cap <= entitled_guest_cap` is a DB check.

Full lists: `ROADMAP.md`, `FEATURES.md`.
