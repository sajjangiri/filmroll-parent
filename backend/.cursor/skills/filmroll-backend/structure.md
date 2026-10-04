# Backend folder map

| Path | Owns |
|---|---|
| `app/main.py` | FastAPI app, CORS, routers |
| `app/api/v1/films.py` | Guest + host HTTP |
| `app/api/v1/billing.py` | Checkout + webhook |
| `app/api/wellknown.py` | Apple associated domain file |
| `app/services/films.py` | Join, reserve, commit, reveal SQL |
| `app/services/storage.py` | Presign PUT/GET, two endpoints |
| `app/services/catalog.py` | Prices (source of truth) |
| `app/services/notify.py` | Host email + guest reveal push |
| `app/services/push.py` | Expo tokens, outbox when `EXPO_PUSH_URL` is empty |
| `app/services/dispatch.py` | Celery after commit |
| `app/worker/celery_app.py` | Queues + beat |
| `app/db/models.py` | `films`, `guests`, `guest_push_tokens`, `shots`, `payments` |
| `tests/` | Integration against compose |

Settings: `app/core/config.py` via env. Local secrets live in `.env` (gitignored). Compose env is the parent `.env` / `.env.example`.
