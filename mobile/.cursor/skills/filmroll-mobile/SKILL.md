---
name: filmroll-mobile
description: Architecture for the Filmroll Expo guest camera (SDK 57). Use when editing mobile/, CameraView, join/gallery screens, deep links, or the FastAPI upload client.
---

# Filmroll mobile (Expo 57 / React Native)

Read https://docs.expo.dev/versions/v57.0.0/ before writing Expo APIs. This is not a host app and not an App Clip.

Product plan: [continue.md](continue.md). Hosts stay on the web (App Store tax). Guests join by code or URL, shoot, and see the gallery after develop.

## Layout

```
App.tsx                      # root: deep link → FilmScreen else HomeScreen
index.ts                     # registerRootComponent
src/api/client.ts            # FastAPI + presigned PUT via expo-file-system/legacy
src/api/types.ts             # snake_case wire types (must match backend / web)
src/queue/                   # disk-first upload queue
src/screens/HomeScreen.tsx
src/screens/FilmScreen.tsx   # join + developed gallery
src/screens/CameraScreen.tsx
app.json                     # scheme filmroll, bundle app.filmroll
```

Keep API code in `src/api/`. Keep screens in `src/screens/`. Do not dump new features into `App.tsx`.

## Contracts that must not drift

- Same upload loop as web: client UUID → reserve → PUT JPEG to `upload_url` → commit. **Never** send photo bytes to FastAPI.
- `uploadAsync` from `expo-file-system/legacy` with `FileSystemUploadType.BINARY_CONTENT` and `Content-Type: image/jpeg`.
- `CameraView` facing is `'front' | 'back'` (not environment/user).
- Guest JWT: AsyncStorage `filmroll-guest-{code}`.
- `EXPO_PUBLIC_API_URL` — `localhost` only works in the simulator; a phone needs the LAN IP. CORS does not apply to native fetch.
- Deep links: `filmroll://f/{code}` and later `https://filmroll.app/f/{code}`. Parse with `filmCodeFromUrl`.
- `crypto.randomUUID()` for shot ids so retries do not burn two slots.

## Do not

- Build an App Clip, StoreKit, or SwiftUI in this app.
- Add host create/pay/moderate screens (that is web).
- Import modern `expo-file-system` `uploadAsync` (v57 moved it to `/legacy`).
- Proxy uploads through Expo or Next.
- Put `node_modules`, `.env`, `.expo`, or generated `/ios` `/android` in git.

## Design patterns

- Screen components own UI. `client.ts` owns HTTP + storage PUT.
- Types stay in `src/api/types.ts` and track `web/lib/types.ts` for shared shapes (`FilmPublic`, reserve/commit/gallery).
- Dark UI, portrait, camera permission string already in `app.json`.
- Offline IndexedDB-style queue exists on web; native uses `src/queue/` (JPEG in documents directory, same shot UUID).

Details: [structure.md](structure.md)
