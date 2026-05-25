"""Celery application.

Configured in Phase 1 so the worker/beat containers boot; business tasks
(Polymarket polling, settlement, email) are added in later phases via
``autodiscover_tasks``.

Run a worker:  celery -A app.celery_app.celery_app worker -l info
Run beat:      celery -A app.celery_app.celery_app beat -l info
"""

from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "xpredict",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
)

# Phase 2+: celery_app.autodiscover_tasks(["app.tasks"])


@celery_app.task(name="health.ping")
def ping() -> str:
    """Trivial liveness task to verify the worker is wired up correctly."""
    return "pong"
