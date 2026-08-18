"""Synchronous session for Celery workers.

The API is async, but Celery tasks are ordinary blocking functions. Rather than
spinning up an event loop per task, workers use a plain psycopg engine.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def get_sync_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_settings().database_url_sync,
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
        )
    return _engine


def get_sync_sessionmaker() -> sessionmaker[Session]:
    global _factory
    if _factory is None:
        _factory = sessionmaker(get_sync_engine(), expire_on_commit=False)
    return _factory


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_sync_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
