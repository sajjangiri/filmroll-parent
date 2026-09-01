# Filmroll API

FastAPI, SQLAlchemy async, Alembic, Celery. Run it from the parent compose stack (`make up` / `make migrate`).

```
app/api/       HTTP
app/services/  domain rules
app/worker/    Celery
app/db/        models
alembic/       migrations
tests/         real Postgres / Redis / MinIO
```

Architecture: `.cursor/skills/filmroll-backend/SKILL.md`

Continue the existing plan: `.cursor/skills/filmroll-backend/continue.md`
