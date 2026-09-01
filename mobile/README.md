# Filmroll mobile

Expo 57 guest camera. Hosts create, pay, and moderate on the **web** — this app
is join, shoot, and gallery only.

## Prerequisites

- Node.js 22+
- A running Filmroll backend (Docker stack from the parent repo)
- **Expo Go** on your phone ([iOS](https://apps.apple.com/app/expo-go/id982107779) / [Android](https://play.google.com/store/apps/details?id=host.exp.exponent))
- Phone and computer on the **same wifi** (physical device)

## Start (iOS Simulator — localhost OK)

Backend first, from the **parent** repo:

```bash
make up && make migrate
```

Then here:

```bash
cp .env.example .env
npm install
npm start
```

Press `i` for the iOS simulator, or scan the QR code with Expo Go.

Default `.env`:

```env
EXPO_PUBLIC_API_URL=http://localhost:8000
```

`localhost` works in the simulator because it shares the Mac's network stack.

## Physical device (step by step)

This is the path most venue tests need. **Three config files** must agree — not
just `mobile/.env`.

### 1. Find your LAN address

On the machine running Docker:

```bash
ipconfig getifaddr en0    # macOS wifi, e.g. 192.168.1.42
```

Use that IP everywhere below (`192.168.1.42` is an example).

### 2. Parent `.env` (repo root)

The API signs presigned upload URLs with `S3_PUBLIC_ENDPOINT_URL`. If this stays
`http://localhost:9000`, join will work but **every upload will fail** — the
phone PUTs to itself.

```env
S3_PUBLIC_ENDPOINT_URL=http://192.168.1.42:9000
PUBLIC_WEB_URL=http://192.168.1.42:3000
CORS_ORIGINS=http://localhost:3000,http://localhost:8081,http://192.168.1.42:3000
```

(`CORS_ORIGINS` is for the browser only; native fetch ignores CORS. Include the
LAN web origin if you also test the PWA on the phone.)

Restart the stack so API and workers reload env:

```bash
make up
```

### 3. Web `.env.local` (optional but needed to create films from the phone browser)

```env
NEXT_PUBLIC_API_URL=http://192.168.1.42:8000
```

Run `npm run dev` in `web/` if you want to create a film from the phone's
browser. You can also create on the laptop at http://localhost:3000 and only
test the Expo app on the phone.

### 4. This app — `mobile/.env`

```env
EXPO_PUBLIC_API_URL=http://192.168.1.42:8000
```

Restart Expo with a clean cache (env is inlined at bundle time):

```bash
npx expo start -c
```

Scan the QR with Expo Go (Android: Expo Go app; iOS: Camera app → open in Expo).

### 5. Run the loop

1. Create a film on the web (laptop or phone browser) — note the 6-character code
2. In Expo: enter the code on the home screen, or open `filmroll://f/{CODE}` if you have a dev build with the scheme
3. Join with a display name
4. Allow camera, shoot a photo
5. On your laptop, MinIO console http://localhost:9001 → bucket `filmroll-shots` → `films/{id}/originals/` should show the JPEG

### Flow

```
Phone (Expo Go)
  │  POST /v1/films/{code}/shots/reserve
  │  POST .../commit
  ▼
API :8000
  │  presigned PUT signed with S3_PUBLIC_ENDPOINT_URL
  ▼
MinIO :9000  ← must be your LAN IP, not localhost
```

## Layout

```
App.tsx              deep links + home vs film screen
src/screens/         HomeScreen, FilmScreen, CameraScreen
src/api/             FastAPI client + wire types (snake_case)
src/queue/           offline JPEG queue (disk first, upload later)
```

Capture: shutter saves JPEG to app storage → queue drains with reserve → PUT →
commit. Same shot UUID on retry so bad wifi does not burn two slots.

## Scripts

```bash
npm start              # Expo dev server
npm run ios            # open iOS simulator
npm run android        # open Android emulator
npx expo start -c      # clear cache after .env change
npm run typecheck      # tsc --noEmit
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|----------------|-----|
| "Network request failed" on join | `EXPO_PUBLIC_API_URL` still `localhost`, or firewall blocking 8000 | Set LAN IP in `mobile/.env`; allow incoming on 8000; `npx expo start -c` |
| Join works, uploads always fail | `S3_PUBLIC_ENDPOINT_URL` still `localhost` | Set LAN IP in parent `.env`, `make up` |
| Changed `.env`, no effect | Expo inlines `EXPO_PUBLIC_*` at bundle time | `npx expo start -c` |
| iOS Simulator | — | `localhost` is fine for API and default MinIO URLs |
| Android Emulator | `localhost` is the emulator, not your Mac | Use `10.0.2.2:8000` and `10.0.2.2:9000` in env files instead of LAN IP |
| CORS error | Browser-only | Irrelevant to Expo; fix `CORS_ORIGINS` only for web PWA on phone |
| Camera permission denied | — | iOS Settings → Expo Go → Camera; or reinstall Expo Go |

## Architecture

- `.cursor/skills/filmroll-mobile/SKILL.md`
- `.cursor/skills/filmroll-mobile/continue.md`

No App Clip, StoreKit, or host tools in this app yet.
