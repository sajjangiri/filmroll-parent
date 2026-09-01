# Filmroll mobile

Expo 57 guest camera. Hosts create and pay on the web.

```
src/screens/         home, film, camera
src/api/             FastAPI client + wire types
src/queue/           offline JPEG queue (disk first, upload later)
```

```bash
cp .env.example .env
npm install
npm start
```

On a physical phone set `EXPO_PUBLIC_API_URL` to the machine's LAN address.

Architecture: `.cursor/skills/filmroll-mobile/SKILL.md`

Continue the existing plan (no App Clip yet): `.cursor/skills/filmroll-mobile/continue.md`
