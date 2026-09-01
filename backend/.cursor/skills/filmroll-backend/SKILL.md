---
name: filmroll-backend
description: Architecture for the Filmroll FastAPI, SQLAlchemy, Celery, and billing backend. Use when editing backend/, films, shots, reveal, entitlements, workers, or AASA.
---

# Filmroll backend (FastAPI)

Python 3.13, `uv`, ruff + mypy strict. Tests use real Postgres/Redis/MinIO via compose (`pytest -m "not load"`). Do not swap in SQLite.

Product plan: [continue.md](continue.md). This API is the source of truth. Web and mobile are clients of the same `/v1` contracts.

## Layout

```
app/api/v1/          # HTTP: films, billing, health
app/api/wellknown.py # AASA at /.well-known/… (not under /v1)
app/core/            # settings, logging
app/db/              # models, async/sync sessions
app/schemas.py       # Pydantic wire types
app/services/        # domain: films, storage, billing, mail, catalog, …
app/worker/          # Celery app + tasks
alembic/             # migrations
tests/               # real stack, not unit fakes for caps/reveal
```

Routers stay thin. Domain rules live in `app/services/`. New tables go through Alembic.

## Invariants (breaking these breaks the product)

1. **Bytes never hit the API.** Reserve a key, return presigned PUT, commit after the object exists. Size/type checked on commit.
2. **Reveal is derived in SQL** (`app/services/films.py`): `revealed_at IS NOT NULL OR now() >= reveal_at`. Do not store an `is_developed` flag flipped by a cron.
3. **Caps serialize with `SELECT … FOR UPDATE`.** Joins lock the film row; shot reserve locks the guest row. A count subquery without a lock double-sells the cap.
4. **`Shot.id` has no server default.** Client UUID. Unique constraint makes retries idempotent.
5. **Celery after commit only** (`enqueue_after_commit`). Queues: `fast` (thumbs, mail, sweep) vs `media` (ZIP, future recap).
6. **Two S3 endpoints.** Sign public URLs with the host a phone can resolve. Internal compose hostname on a signed URL is a user-facing outage.
7. **Private bucket.** Signed GET only after develop (or host review). Hidden shots never fan out.
8. **`guest_cap <= entitled_guest_cap`.** Raising the cap is Checkout, not PATCH. Catalog is `app/services/catalog.py`, not Stripe Products.
9. **Charge for capacity, not shutter presses.** Fake Checkout locally (`BILLING_FAKE`); ignored in production.
10. **Host email is never on `FilmPublic`.** Recover always 204 (no enumeration).
11. **AASA** is JSON, no redirect, placeholder Team ID until App Store Connect.
12. **An `EXPIRED` shot id is spent.** Committing one would put the photo in the gallery while the replacement slot is still outstanding, letting a guest shoot past the limit one rejected upload at a time. A retry must reserve a new id.
13. **`_release_reservation` commits itself.** Callers raise immediately after and the session dependency rolls back on exception, so a plain flush would silently cost the guest a shot.
14. **Tokens are scoped to one film.** `deps.py` compares `principal.film_id` to the loaded film; without it a guest at one event could act inside another.
15. **The rate limiter fails open.** Redis is not the source of truth, and a limiter outage that blocked every guest at a wedding is worse than the burst it prevents.

## Tests

`conftest.py` sets env **before** app import. Schema: `drop_all` + `DROP TYPE shot_state` + `create_all`. `SMTP_HOST=""` so mail hits `app.services.mail.outbox`.

Details: [structure.md](structure.md)
