from celery import Celery

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging()

celery_app = Celery(
    "filmroll",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Redelivery on worker death. Every task in this app is written to be
    # idempotent, which is what makes at-least-once delivery safe.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Long media jobs must not be hoarded by an idle worker. Prefetching one at
    # a time keeps a queued encode available to whichever worker frees up first.
    worker_prefetch_multiplier=1,
    task_default_queue="fast",
    # Splitting the queues is the reason a four-minute recap encode cannot
    # stall hundreds of thumbnail jobs behind it.
    task_routes={
        "app.worker.tasks.generate_derivatives": {"queue": "fast"},
        "app.worker.tasks.sweep_abandoned_reservations": {"queue": "fast"},
        "app.worker.tasks.purge_film_objects": {"queue": "fast"},
        "app.worker.tasks.build_recap_video": {"queue": "media"},
        "app.worker.tasks.build_export_archive": {"queue": "media"},
    },
    task_annotations={
        "app.worker.tasks.build_recap_video": {
            "soft_time_limit": 600,
            "time_limit": 900,
        },
        "app.worker.tasks.generate_derivatives": {
            "soft_time_limit": 60,
            "time_limit": 120,
        },
    },
    beat_schedule={
        "sweep-abandoned-reservations": {
            "task": "app.worker.tasks.sweep_abandoned_reservations",
            "schedule": 300.0,
        },
    },
)
