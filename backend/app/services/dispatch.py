"""Deferred task dispatch.

Enqueuing a Celery task inside an open transaction is a classic and painful
bug: the worker can pick the message up and query for a row that has not been
committed yet, or worse, act on a transaction that ends up rolling back. Redis
knows nothing about Postgres transactions.

Tasks registered here are held until the session actually commits, and are
dropped entirely if it does not.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.logging import get_logger

_PENDING = "_pending_task_dispatch"
log = get_logger(__name__)


def enqueue_after_commit(session: AsyncSession | Session, task_name: str, *args: Any) -> None:
    """Queue a task to be sent once the surrounding transaction commits."""
    target = session.sync_session if isinstance(session, AsyncSession) else session
    target.info.setdefault(_PENDING, []).append((task_name, args))


@event.listens_for(Session, "after_commit")
def _send_pending(session: Session) -> None:
    pending = session.info.pop(_PENDING, [])
    if not pending:
        return

    # Imported lazily so the API process does not pull in worker dependencies,
    # and so tests can patch the Celery app.
    from app.worker.celery_app import celery_app

    for task_name, args in pending:
        try:
            celery_app.send_task(task_name, args=list(args))
        except Exception as exc:  # pragma: no cover - broker outage
            # The data is already committed and durable. Losing a derivative
            # job degrades the gallery to originals rather than losing a photo,
            # so this must never surface as a request failure.
            log.error("dispatch.failed", task=task_name, error=str(exc))


@event.listens_for(Session, "after_rollback")
def _drop_pending(session: Session) -> None:
    session.info.pop(_PENDING, None)
