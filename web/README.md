# Filmroll web

Next.js guest camera and host tools. The browser talks to FastAPI directly;
photo bytes never pass through this app.

## Prerequisites

- Node.js 22+
- A running Filmroll backend (Docker stack from the parent repo)

## Start (localhost)

Backend first, from the **parent** repo:

```bash
make up && make migrate
```

Then in this directory:

```bash
cp .env.example .env.local
npm install
npm run dev
```

Open http://localhost:3000

| URL | Who |
|-----|-----|
| `/` | Host — create a film |
| `/f/{code}` | Guest — join and shoot |
| `/f/{code}/host` | Host — dashboard, hide, billing, export |
| `/f/{code}/gallery` | Guest — developed album |
| `/f/{code}/print` | Host — table cards |

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | FastAPI base URL (browser calls this directly) |

Nothing is proxied through Next.js. Guest capture is reserve → presigned PUT →
commit, same contract as the Expo app.

## Physical phone (PWA in the browser)

Phone and laptop on the **same wifi**. Find your machine's address:

```bash
ipconfig getifaddr en0    # macOS wifi, e.g. 192.168.1.42
```

Edit **three** places (replace `192.168.1.42` with yours):

**1. Parent `.env`** (repo root):

```env
S3_PUBLIC_ENDPOINT_URL=http://192.168.1.42:9000
PUBLIC_WEB_URL=http://192.168.1.42:3000
CORS_ORIGINS=http://localhost:3000,http://localhost:8081,http://192.168.1.42:3000
```

**2. This file — `web/.env.local`:**

```env
NEXT_PUBLIC_API_URL=http://192.168.1.42:8000
```

**3. Restart backend** from the parent repo:

```bash
make up
```

**4. Restart Next** (env is baked in at dev start):

```bash
npm run dev
```

On the phone, open `http://192.168.1.42:3000`, create or join a film, allow
camera access. After shooting, confirm the object in MinIO console
(http://localhost:9001 on your laptop).

Why three files? The API signs upload URLs with `S3_PUBLIC_ENDPOINT_URL`. If that
still says `localhost`, the phone PUTs to itself and every shot fails after
join.

## Layout

```
app/                 App Router pages (thin — await params, render one screen)
components/guest/    Camera, join, gallery, install hint
components/host/     Create, dashboard, print cards
components/pwa/      Service worker registration
lib/                 API client, types, IndexedDB upload queue
public/sw.js         PWA worker (no fetch handler — see web skill)
```

## Scripts

```bash
npm run dev      # Next dev server (port 3000)
npm run build    # production build
npm run lint     # ESLint (not next lint — Next 16)
npx tsc --noEmit # typecheck
```

## Architecture

Read before changing code:

- `.cursor/skills/filmroll-web/SKILL.md`
- `.cursor/skills/filmroll-web/continue.md`

Mobile guest camera and App Clip are separate repos; hosts stay on the web.
