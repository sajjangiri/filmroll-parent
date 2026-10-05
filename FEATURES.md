# Filmroll — full feature list

Legend:

- **Status** — `done` (shipped in the prototype), `todo`
- **Phase** — see `ROADMAP.md`
- **Priority** — `P0` cannot launch without it · `P1` needed to win a wedding ·
  `P2` moat / later
- **Surface** — `web` PWA guest+host · `ios` full native app · `clip` App Clip ·
  `android` · `api` server

---

## 1. Film / event lifecycle

| Feature | Status | Phase | Pri | Surface |
|---|---|---|---|---|
| Create a film (name, cover, event type) | done | 0 | P0 | web, ios |
| Set how long the film stays open | done | 0 | P0 | web, ios |
| Set reveal / develop time | done | 0 | P0 | web, ios |
| Shots per guest (film roll size) | done | 0 | P0 | web, ios |
| Guest cap | done | 0 | P0 | web, ios |
| Short film code (6 chars, QR-friendly) | done | 0 | P0 | api |
| Instant reveal mode (live gallery) | done | 3 | P1 | web, ios |
| Extend time / raise cap mid-event | done | 3 | P1 | web, ios, android |
| Change the develop time after create | done | 3 | P1 | web, ios, android |
| Multiple rolls per event (ceremony / party) | todo | 6 | P2 | web, ios |
| Duplicate a past film as a template | todo | 6 | P2 | web |
| Archive / delete a film | done | 3 | P1 | web |
| Guided create: three short steps on web, one screen in the app | done | 3 | P1 | web, ios, android |
| Landing page that explains the film and starts one | done | 3 | P1 | web |

## 2. Guest join

| Feature | Status | Phase | Pri | Surface |
|---|---|---|---|---|
| QR code join | done | 0 | P0 | all |
| Share link join | done | 0 | P0 | all |
| No account, name only | done | 0 | P0 | all |
| Guest identity persists on device | done | 0 | P0 | web, ios, clip |
| **App Clip launch from QR (no download)** | todo | 5 | P1 | clip |
| App Clip Codes (Apple visual code) | todo | 5 | P2 | clip |
| NFC table tags | todo | 6 | P2 | ios, android |
| Android/desktop fallback to PWA on same URL | done | 2 | P0 | web |
| Optional PIN on the film | done | 3 | P1 | api, web, ios |
| Geo or time-window lock | todo | 6 | P2 | api |
| Guest list import (CSV) | todo | 6 | P2 | web |
| Smart App Banner offering the iOS app | done | 5 | P1 | web |
| "Your roll" home: shots left, upload state, develop countdown | done | 2 | P1 | web, ios, android |
| Develop-time reminder (calendar file on web, reveal push in the app) | done | 3 | P1 | web, ios, android |

## 3. Camera + capture

| Feature | Status | Phase | Pri | Surface |
|---|---|---|---|---|
| In-browser camera capture | done | 0 | P0 | web, clip |
| Native camera capture | done | 5 | P1 | ios |
| Server-enforced shot limit | done | 0 | P0 | api |
| Shot counter ("8 left") | done | 0 | P0 | web, ios, clip |
| **Offline capture + upload queue** | done | 2 | P0 | web, ios |
| Retry with backoff, resumable upload | done | 2 | P0 | web, ios |
| Visible upload queue state | done | 2 | P0 | web, ios |
| Front / back camera switch | done | 2 | P0 | web, ios, clip |
| Flash / torch | done | 2 | P1 | web, ios |
| Live filter preview (WebGL / Core Image) | done | 2 | P1 | web |
| Film look developed into every guest copy (matches the preview) | done | 2 | P1 | api |
| Camera styles: warm, faded, mono, changeable until the album opens | done | 3 | P1 | api, web, ios, android |
| Optional date stamp on photos | done | 3 | P1 | api, web, ios, android |
| Originals stored clean, look applied at display | done | 1 | P1 | api |
| Idempotent shot IDs (no double burn) | done | 1 | P0 | api |
| Camera-roll upload (host toggle, spends a shot, until the album opens) | done | 6 | P2 | api, web, ios, android (**not** clip) |
| Guest video clips (≤15s) | done | 6 | P2 | web, ios, android |

## 4. Reveal + gallery

| Feature | Status | Phase | Pri | Surface |
|---|---|---|---|---|
| Delayed reveal | done | 0 | P0 | all |
| Host "develop now" override | done | 0 | P0 | web, ios |
| Per-photo attribution | done | 0 | P0 | all |
| **Signed URLs that 403 before reveal** | done | 1 | P0 | api |
| Thumbnail / display derivatives | done | 1 | P0 | api |
| Bulk ZIP of originals | done | 3 | P1 | web, ios |
| Guest saves a single photo | done | 3 | P1 | web, ios, android |
| Full-screen photo viewer (swipe, save, report) | done | 3 | P1 | web, ios, android |
| Reveal notification (email / push) | done | 3 | P1 | web, ios |
| Ephemeral reveal notification (8h/24h) | todo | 5 | P2 | clip |
| Live slideshow for a venue screen | done | 6 | P2 | web |
| Recap video, 45–90s with music | todo | 6 | P2 | api |
| Favorites / hearts | done | 6 | P2 | web, ios, android |

## 5. Host controls, trust and safety

| Feature | Status | Phase | Pri | Surface |
|---|---|---|---|---|
| Host dashboard (guests, shots, health) | done | 0 | P0 | web, ios |
| Durable host auth (magic link / Apple) | done | 1 | P0 | web, ios |
| **One-tap hide / moderation queue** | done | 3 | P0 | web, ios |
| Hidden photos never fan out | done | 3 | P0 | api |
| Co-hosts | done | 3 | P1 | web, ios, android |
| Remove a guest (camera stops, seat freed, photos hidden by default) | done | 3 | P1 | api, web, ios, android |
| Photographer read-only seat | done | 3 | P2 | web, ios, android |
| Guest deletes own photo | done | 3 | P1 | api |
| Private vs shared visibility | done | 3 | P1 | web, ios |
| Report a photo | done | 3 | P1 | web, ios |
| NSFW detection assist (host decides) | todo | 6 | P2 | api |
| Print-ready QR table cards (PDF) | done | 3 | P1 | web |

## 6. Billing

| Feature | Status | Phase | Pri | Surface |
|---|---|---|---|---|
| Free tier (5 guests, full features) | done | 4 | P0 | api |
| **Stripe Checkout on web, by guest cap** | done | 4 | P0 | web |
| Local payment methods for Nepal (Khalti / eSewa) | todo | 4 | P0 | api, web |
| Server-side entitlement enforcement | done | 4 | P0 | api |
| Upgrade cap mid-event | done | 4 | P1 | web, ios |
| StoreKit 2 IAP (full app only) | todo | 5 | P1 | ios |
| Unlimited-shots add-on | done | 4 | P1 | web, ios |
| Video pack add-on | done | 4 | P2 | web (bought), ios/android (used) |
| Receipts, refunds, VAT/tax | done | 4 | P1 | web, api |
| Keep-forever storage after 12 months | done | 4 | P1 | web |
| Photobook / prints | todo | 6 | P2 | web |
| Planner / venue license, invoicing | todo | 6 | P2 | web |
| Brand rights pack + event analytics | todo | 6 | P2 | web |

## 7. Platform / infrastructure

| Feature | Status | Phase | Pri | Surface |
|---|---|---|---|---|
| Postgres schema + migrations | done | 1 | P0 | api |
| Object storage, signed direct upload | done | 1 | P0 | api |
| Derivatives worker | done | 1 | P0 | api |
| Self-hosted QR generation | done | 1 | P0 | api |
| Rate limiting + abuse protection | done | 1 | P0 | api |
| Installable PWA + service worker | done | 2 | P0 | web |
| i18n (EN, ES, FR) | done | 2 | P1 | web, ios |
| Accessibility pass (guest flow) | done | 2 | P1 | web, ios |
| Event-day observability dashboards | done | 1 | P1 | api, web |
| AASA + assetlinks + `applinks:` entitlement | done | 5 | P1 | api, ios, android |
| App Clip `appclips:` entitlement | todo | 5 | P1 | clip |
| Android host app | done | 6 | P2 | android |

---

## What an App Clip specifically cannot do

These are Apple platform limits, not design choices. They decide what the QR
experience can include. Details and sources in `docs/app-clip.md`.

| Capability | In App Clip | Consequence for Filmroll |
|---|---|---|
| Camera + microphone | Yes | The guest camera works in the clip |
| Photo library read/write | **No** | No camera-roll upload; save via share sheet |
| Background upload / `URLSession` background | **No** | Uploads must finish while the clip is open |
| In-app purchase | **No** | Host buys in the full app or on the web |
| Persistent local storage | **No** (ephemeral, ~8h idle) | Guest identity must live server-side |
| Push notifications | Ephemeral only (8h / 24h) | Reveal ping works only for a short window |
| Location | When-in-use only | Geo-lock is possible, background geo is not |
| Binary size (QR invocation) | **15 MB uncompressed** | Clip = camera + upload only, nothing else |

**Design conclusion:** the App Clip is a thin capture surface. Every heavier
job — browsing the gallery, downloading originals, paying, moderating — belongs to
the web app or the full native app.
