---
name: filmroll-web
description: Architecture and conventions for the Filmroll Next.js guest camera and host tools. Use when editing web/, App Router pages, camera, PWA queue, host dashboard, or billing UI.
---

# Filmroll web (Next.js App Router)

Read `node_modules/next/dist/docs/` in this folder before writing Next code. This is Next 16: `params` is a `Promise`; there is no `next lint` (ESLint CLI). Do not sync `setState` in effects (React 19).

Product plan: do not fork it. Continue from [continue.md](continue.md). Hosts create, pay, and moderate **here**. Mobile is guests only.

## Layout (keep related files together)

```
app/                         # routes only
  page.tsx                   # create film
  f/[code]/page.tsx          # guest join + camera
  f/[code]/host/page.tsx     # host inbox
  f/[code]/gallery/page.tsx
  f/[code]/print/page.tsx
components/
  guest/                     # Camera, GuestApp, Gallery, InstallHint
  host/                      # CreateFilmForm, HostDashboard, PrintCards
  pwa/                       # RegisterServiceWorker
lib/                         # api client, types, IndexedDB upload queue
public/sw.js
```

Do not put API routes in Next that proxy photo bytes. The browser talks to FastAPI (`NEXT_PUBLIC_API_URL`) and PUTs to storage.

## Contracts that must not drift

- Types in `lib/types.ts` mirror backend JSON **snake_case**. Do not camelCase on the way in.
- Capture: client UUID → `POST /v1/films/{code}/shots/reserve` → presigned PUT → `POST .../commit`. Same as mobile.
- Offline: shutter writes JPEG to IndexedDB first (`lib/upload-queue.ts`). Drain when the page is open. iOS will not Background Sync.
- Guest token: `localStorage` key `filmroll-guest-{code}`. Host token: `filmroll-host-{code}`.
- Public `FilmPublic` never includes host email.
- Gallery photos are empty until developed; do not invent client-side reveal.
- Billing: Stripe Checkout on web. PATCH must not raise `guest_cap` above entitlement; 402 means pay.

## Patterns

- Client components only where they need the camera, queue, or host session.
- Route files stay thin: await `params`, render one screen component.
- New guest UI goes in `components/guest/`. New host UI in `components/host/`.
- PWA: `app/manifest.ts` + `public/sw.js`. Do not cache API JSON (client already `cache: "no-store"`).

## Deliberate choices that look like bugs

- **`public/sw.js` has no fetch handler.** Next payloads are versioned per build, so caching them would serve a stale app after a deploy. Capture does not need the worker: photos land in IndexedDB from the page and the drain loop runs whenever this origin is open.
- **Turbopack root is pinned one level up** (`next.config.ts`). A stray lockfile in the parent makes Turbopack infer the wrong workspace root, which changes how files resolve. Do not "correct" it to this directory.

## Do not

- Start an App Clip or Smart App Banner without a real App Store id.
- Route uploads through Next.js.
- Bake a filter into the stored original (preview only, later WebGL work).
- Add StoreKit.

Details: [structure.md](structure.md)
