# Filmroll web

Next.js guest camera and host tools. The browser talks to FastAPI directly; photo bytes never pass through this app.

```
app/                 routes
components/guest/    join, camera, gallery
components/host/     create, dashboard, print
components/pwa/      service worker registration
lib/                 API client, types, offline upload queue
```

```bash
cp .env.example .env.local
npm install
npm run dev
```

Architecture (do not invent a new one): `.cursor/skills/filmroll-web/SKILL.md`

Continue the existing Filmroll plan: `.cursor/skills/filmroll-web/continue.md`
