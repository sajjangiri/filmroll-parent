# Mobile folder map

| Path | Owns |
|---|---|
| `App.tsx` | Linking + home / create / host / guest routing |
| `src/screens/` | Home, create film, host share, film (join/gallery), camera |
| `src/api/client.ts` | REST + presigned PUT |
| `src/api/types.ts` | Wire types |
| `src/queue/` | Offline JPEG queue + drain hook |
| `src/notifications.ts` | Expo token after join; tap opens the film |
| `app.json` | name Filmroll, scheme `filmroll`, bundle `app.filmroll`, camera + notifications plugins |
| `.env.example` | `EXPO_PUBLIC_API_URL` |

Expo Go on a phone cannot use `localhost`. Generated `ios/` and `android/` are gitignored until a dedicated native build is intentional.
