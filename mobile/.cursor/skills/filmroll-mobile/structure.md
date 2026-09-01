# Mobile folder map

| Path | Owns |
|---|---|
| `App.tsx` | Linking + which screen is open |
| `src/screens/` | Home, film (join/gallery), camera |
| `src/api/client.ts` | REST + presigned PUT |
| `src/api/types.ts` | Wire types |
| `src/queue/` | Offline JPEG queue + drain hook |
| `app.json` | name Filmroll, scheme `filmroll`, bundle `app.filmroll`, camera plugin |
| `.env.example` | `EXPO_PUBLIC_API_URL` |

Expo Go on a phone cannot use `localhost`. Generated `ios/` and `android/` are gitignored until a dedicated native build is intentional.
