# Web folder map

| Path | Owns |
|---|---|
| `app/` | App Router pages, layout, manifest, icons. No business logic. |
| `components/guest/` | Join, camera, gallery, slideshow, install hint |
| `components/host/` | Create, dashboard, print cards |
| `components/pwa/` | Service worker registration |
| `lib/api.ts` | FastAPI client, tokens, reserve/commit/checkout |
| `lib/types.ts` | Wire types, snake_case |
| `lib/upload-queue.ts` | IndexedDB queue |
| `lib/use-upload-queue.ts` | React binding for the queue |
| `public/sw.js` | PWA worker |

Routes:

- `/` create
- `/f/{code}` guest
- `/f/{code}/host` moderate (photos before public gallery)
- `/f/{code}/gallery` after develop
- `/f/{code}/slideshow` venue wall (public gallery only)
- `/f/{code}/print` table cards
