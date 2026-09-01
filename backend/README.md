# Filmroll API

FastAPI, SQLAlchemy async, Alembic, Celery. Photo bytes never pass through this
process — clients reserve a slot, PUT to MinIO with a presigned URL, then
commit.

This repo is usually developed inside the parent Filmroll monorepo. The compose
files live one level up; run `make up` from the repo root, not from here.

```
app/api/       HTTP (films, billing, health, AASA)
app/services/  domain rules
app/worker/    Celery tasks
app/db/        models + sessions
alembic/       migrations
tests/         real Postgres / Redis / MinIO
```

## Prerequisites

- Docker Desktop (or Docker Engine + Compose v2)
- Ports free on the host: **8000**, **5432**, **6379**, **9000**, **9001**, **8025**

## Start the stack

From the **parent** repo root (where `docker-compose.yml` lives):

```bash
cp .env.example .env          # first time only
make up                       # builds and starts everything, waits for health
make migrate                  # applies Alembic migrations
```

Check it:

- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/healthz
- MinIO console: http://localhost:9001 (`filmroll` / `filmroll-dev-secret`)
- Mailpit (magic links, reveal email): http://localhost:8025

End-to-end smoke test from the parent repo:

```bash
python3 scripts/smoke.py
```

## Published ports (local override)

| Port | Service | Use |
|------|---------|-----|
| 8000 | `api` | FastAPI |
| 5432 | `db` | Postgres |
| 6379 | `redis` | Celery broker |
| 9000 | `minio` | S3 API — **presigned upload URLs are signed against this host** |
| 9001 | `minio` | Web console |
| 8025 | `mailpit` | Inbox UI |
| 1025 | `mailpit` | SMTP (API sends here locally) |
| 5555 | `flower` | Celery UI (`docker compose --profile tools up -d`) |

## Environment

Configuration is in the parent `.env` (copy from `.env.example`). This checkout
also ships `backend/.env.example` as a mirror of the API-relevant keys.

Important keys:

| Variable | Default (local) | Notes |
|----------|-----------------|-------|
| `DATABASE_URL` | `...@db:5432/filmroll` | Host `db` is the compose service name |
| `S3_ENDPOINT_URL` | `http://minio:9000` | Internal — workers and API HEAD/DELETE |
| `S3_PUBLIC_ENDPOINT_URL` | `http://localhost:9000` | **Presigned PUT/GET URLs** — must be a host the phone can open |
| `PUBLIC_WEB_URL` | `http://localhost:3000` | Join URLs and QR codes |
| `CORS_ORIGINS` | `http://localhost:3000,...` | Browser origins only |
| `BILLING_FAKE` | `true` | Fake Checkout until `STRIPE_SECRET_KEY` is set |

For a **physical phone** on the same wifi, set `S3_PUBLIC_ENDPOINT_URL` to your
machine's LAN address (see [mobile/README.md](../mobile/README.md) in the parent
repo, or the parent README).

After editing `.env`, restart the stack so workers pick up new values:

```bash
make up
```

## Make targets (parent repo)

Run from the parent directory:

```bash
make help        # list all targets
make up          # start stack
make down        # stop, keep volumes
make clean       # stop and destroy volumes
make migrate     # alembic upgrade head
make test        # full pytest suite
make test-fast   # everything except load test
make lint        # ruff + mypy
make logs        # tail all services
make psql        # psql into dev database
make shell       # bash in api container
```

## Tests

```bash
make test-fast
```

Tests use real Postgres, Redis, and MinIO (`filmroll_test` database). SQLite is
not substituted — cap locks and SQL `now()` reveal are part of what ships.

## Architecture

Do not invent a new layout. Read:

- `.cursor/skills/filmroll-backend/SKILL.md`
- `.cursor/skills/filmroll-backend/continue.md`
