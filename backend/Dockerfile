# syntax=docker/dockerfile:1

# The virtualenv deliberately lives outside /app. In local development the repo
# is bind-mounted over /app for hot reload, and a venv inside /app would be
# shadowed by that mount, leaving the container with no dependencies.
ARG PYTHON_VERSION=3.13
ARG VENV=/opt/venv

# --------------------------------------------------------------------- builder
FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm-slim AS builder
ARG VENV
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=${VENV}

WORKDIR /app

# Dependencies resolve in their own layer so application edits do not
# invalidate the dependency cache.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --all-groups

# --------------------------------------------------------------------- runtime
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime
ARG VENV
ENV PATH="${VENV}/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --create-home app

COPY --from=builder --chown=app:app ${VENV} ${VENV}

WORKDIR /app
COPY --chown=app:app . .

USER app
EXPOSE 8000

# The slim image has no curl, so probe with the interpreter that is already here.
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz', timeout=4).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ----------------------------------------------------------------------- media
# Only the media worker needs ffmpeg. Keeping it out of the API image saves
# roughly 200 MB on the service that scales the most.
FROM runtime AS media
USER root
RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg \
    && rm -rf /var/lib/apt/lists/*
USER app
HEALTHCHECK NONE
CMD ["celery", "-A", "app.worker.celery_app", "worker", "-Q", "media", "--concurrency", "1", "--loglevel", "info"]
