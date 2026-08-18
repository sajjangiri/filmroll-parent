# Filmroll

A shared disposable camera for events. Guests scan a QR code, join without an
account or a download, take a limited number of photos, and the whole roll
develops at a time the host chooses.

## Quick start

Requires Docker.

```bash
make up        # builds and starts everything, waits for health
make migrate   # applies database migrations
make test      # runs the suite
```

Then:

- API and interactive docs: http://localhost:8000/docs
- MinIO console: http://localhost:9001 (`filmroll` / `filmroll-dev-secret`)
- `make help` lists every target

To check the whole loop against a running stack:

```bash
python3 scripts/smoke.py
```

## Architecture

```
web/       Next.js, becoming the no-download guest camera
mobile/    Expo host app (not started)
backend/   FastAPI, Celery workers, Alembic migrations
```

Services, all defined in `docker-compose.yml`:

| Service        | Role                                             |
| -------------- | ------------------------------------------------ |
| `api`          | FastAPI, presigns uploads and enforces the rules  |
| `db`           | Postgres 17, the only source of truth             |
| `redis`        | Celery broker                                     |
| `minio`        | S3-compatible storage, private bucket             |
| `worker-fast`  | Thumbnails and sweeps, high concurrency           |
| `worker-media` | ffmpeg and archives, concurrency 1                |
| `beat`         | Scheduled cleanup and notifications               |

The queues are split deliberately: a single four-minute recap encode on a shared
queue would stall hundreds of thumbnail jobs and leave every guest watching a
spinner.

## Design decisions worth keeping

**Photo bytes never pass through the API.** Clients reserve a slot, upload
directly to object storage with a presigned URL, then commit. A 150-guest
wedding is roughly 3000 photos and 15 GB; routing that through the app tier
would demand real infrastructure, and avoiding it means a small container copes.

**Reveal is derived, never a stored flag.** It is computed in SQL as
`revealed_at IS NOT NULL OR now() >= reveal_at`, using the database clock. Had a
scheduled job owned that boolean, one dead worker would mean a wedding gallery
that silently never opens.

**Caps are enforced with a row lock, not just a conditional insert.** Under
READ COMMITTED the count subquery takes no lock, so two simultaneous
reservations both observe `limit - 1` and both succeed. Since the caps are the
pricing tiers, that race gives away revenue. Reservations serialise on the guest
row, joins on the film row.

**Shot ids come from the client.** Venue wifi guarantees retries, and a
client-generated id means every retry collapses onto the same row and the same
object instead of burning slots.

**Background work is dispatched after commit.** Redis knows nothing about
Postgres transactions, so enqueuing inline lets a worker query for a row that
was never committed.

**Photos are private by default.** The bucket denies anonymous access and images
are reachable only through short-lived signed URLs, minted after the film has
developed.

## Testing

```bash
make test        # everything
make test-fast   # excludes the load suite, used by the pre-push hook
```

Tests run against real Postgres, Redis and MinIO on a dedicated database and
bucket. SQLite is not substituted: cap enforcement is a raw conditional insert
with row locks and reveal evaluates Postgres `now()`, so an in-memory database
would exercise behaviour that does not ship.

Enable the push gate once per clone:

```bash
git config core.hooksPath .githooks
```

Pushes to `main` or `develop` then run the fast suite first. It is a
convenience, not a boundary, since `--no-verify` bypasses it; branch protection
with a required CI check is the real enforcement.

## Going to production

Storage is addressed purely through the S3 API and every dependency is a URL, so
deployment is a configuration change rather than a code change. Point
`DATABASE_URL`, `REDIS_URL` and `S3_ENDPOINT_URL` at managed services.

Cloudflare R2 is the recommended storage target, because egress dominates the
cost curve for a photo gallery and R2 does not charge for it.

Note `S3_PUBLIC_ENDPOINT_URL` is separate from `S3_ENDPOINT_URL`. Presigned URLs
are signed against a specific host and are opened by a phone, so they must be
signed for a host that phone can resolve; workers use the internal endpoint.
