"""Celery factory + beat scheduler + Sentry init + beat heartbeat thread (D-28, D-29, D-41).

Two signal-driven init points:
  - worker_process_init.connect → configure_logging + init_sentry(service="worker")
  - beat_init.connect           → configure_logging + init_sentry(service="beat")
                                + heartbeat daemon thread (Pattern 1, Pitfall 1)

structlog contextvars are cleared on task_prerun + task_postrun (Pitfall 7);
task_prerun also binds task_id / task_name for log correlation (D-26).

Beat heartbeat: touches /tmp/celerybeat.heartbeat every 30s so the
docker-compose healthcheck (D-03) can detect a dead beat via mtime.

Empty beat_schedule = {} — Phases 2-9 append their periodic tasks here.
"""

from __future__ import annotations

import contextlib
import threading
import time
from pathlib import Path
from typing import Any

import structlog
from celery import Celery
from celery.schedules import crontab
from celery.signals import beat_init, task_failure, task_postrun, task_prerun, worker_process_init
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from app.core.config import Settings
from app.core.logging import configure_logging
from app.core.sentry import init_sentry

settings = Settings()

celery_app = Celery(
    "xpredict",
    broker=str(settings.REDIS_URL),
    backend=str(settings.REDIS_URL),
    include=[
        "app.integrations.polymarket.tasks",
    ],
)
celery_app.conf.beat_scheduler = "redbeat.RedBeatScheduler"
celery_app.conf.redbeat_redis_url = str(settings.REDIS_URL)
celery_app.conf.beat_schedule = {
    # Phase 6 — Polymarket sync (MKT-05, MKT-06)
    "poll-polymarket-top25": {
        "task": "app.integrations.polymarket.tasks.poll_polymarket_top25",
        "schedule": 30.0,
    },
    "snapshot-odds": {
        "task": "app.integrations.polymarket.tasks.snapshot_odds",
        "schedule": 300.0,
    },
    # Phases 7-9 append tasks here
    # Phase 7 — Polymarket auto-resolution (STL-01): detect UMA-resolved markets every 60s
    "detect-polymarket-resolutions": {
        "task": "app.integrations.polymarket.tasks.detect_polymarket_resolutions",
        "schedule": 60.0,
    },
}
# Route all tasks to the "default" queue so worker (-Q default) picks them up.
# Without this, Celery's library default is "celery" and tasks queue there
# while the worker idles on "default" (silent stall in production).
celery_app.conf.task_default_queue = "default"
celery_app.conf.task_default_exchange = "default"
celery_app.conf.task_default_routing_key = "default"

# Periodic schedule (RedBeat — stored in Redis, loaded by beat on restart).
# Phases 2-9 each .update() this dict; never reassign it (D-?? shared schedule).
# Phase 3 SC#7 / PLT-09: nightly ledger-vs-cache drift reconciliation at 03:00 UTC
# (Claude's Discretion — low-traffic window).
celery_app.conf.beat_schedule.update(
    {
        "reconcile-wallets-nightly": {
            "task": "app.wallet.reconcile.reconcile_wallets",
            "schedule": crontab(hour=3, minute=0),
        },
    }
)


# Path used by the beat heartbeat thread (D-03 healthcheck reads its mtime)
HEARTBEAT_PATH = Path("/tmp/celerybeat.heartbeat")
_HEARTBEAT_INTERVAL_SECONDS = 30


def _heartbeat_loop() -> None:
    """Touch HEARTBEAT_PATH every 30s — docker-compose healthcheck reads mtime."""
    while True:  # pragma: no cover  — covered by integration smoke
        # /tmp/celerybeat.heartbeat may be unavailable on Windows host runs of
        # `celery beat` — we still don't want the worker to crash.
        with contextlib.suppress(OSError):
            HEARTBEAT_PATH.touch()
        time.sleep(_HEARTBEAT_INTERVAL_SECONDS)


@worker_process_init.connect
def _init_worker(**_kwargs: Any) -> None:
    """Configure logging + Sentry per worker process. NEVER at module-level (Pitfall 5)."""
    configure_logging(settings)
    init_sentry(
        service="worker",
        settings=settings,
        integrations=[CeleryIntegration(), SqlalchemyIntegration()],
    )


@beat_init.connect
def _init_beat(**_kwargs: Any) -> None:
    """Configure logging + Sentry + start heartbeat thread inside the beat process.

    Heartbeat thread is started FIRST so it runs even when acquire_distributed_beat_lock
    (RedBeat's beat_init receiver) blocks waiting for the distributed lock — which can
    happen when beat restarts while a previous run's lock is still held in Redis.
    """
    threading.Thread(target=_heartbeat_loop, daemon=True, name="celerybeat-heartbeat").start()
    configure_logging(settings)
    init_sentry(
        service="beat",
        settings=settings,
        integrations=[CeleryIntegration(), SqlalchemyIntegration()],
    )


@task_prerun.connect
def _on_task_prerun(task_id: str | None = None, task: Any = None, **_kwargs: Any) -> None:
    """Clear stale contextvars + bind this task's id/name (Pitfall 7)."""
    structlog.contextvars.clear_contextvars()
    if task is not None:
        structlog.contextvars.bind_contextvars(
            task_id=task_id,
            task_name=task.name,
        )


@task_postrun.connect
def _on_task_postrun(**_kwargs: Any) -> None:
    """Drop the task's contextvars before the worker accepts the next task."""
    structlog.contextvars.clear_contextvars()


@task_failure.connect
def _on_task_failure(
    task_id: str | None = None,
    exception: BaseException | None = None,
    **_kwargs: Any,
) -> None:
    """Belt-and-suspenders Sentry capture for task failures.

    CeleryIntegration auto-captures via its own task_failure subscriber, but
    initialising Sentry in worker_process_init (after Celery has already
    wired its signal dispatch table) means the integration's subscriber is
    not always reachable. This explicit handler guarantees every uncaught
    task exception is reported to Sentry tagged service=worker.
    """
    if exception is None:
        return
    import sentry_sdk

    sentry_sdk.capture_exception(exception)


@celery_app.task(name="app.core.sentry.sentry_test_task")
def sentry_test_task() -> None:
    """Synthetic Sentry trigger inside the Celery worker (D-29).

    Trigger via flower UI ("Tasks" → call) or:
        celery -A app.celery_app call app.core.sentry.sentry_test_task
    """
    raise RuntimeError("sentry test from worker")


# --------------------------------------------------------------------------- #
# Task module registration (Pitfall 5 — task reachability).
#
# Periodic-task modules whose tasks are declared with @celery_app.task in a
# SEPARATE module must be imported so the worker/beat process registers them;
# an unregistered task makes beat fire into a silent no-op (T-03-22). This
# import is placed at the BOTTOM of the module on purpose: ``celery_app`` is
# fully constructed above, so ``app.wallet.reconcile``'s
# ``from app.celery_app import celery_app`` resolves cleanly (no circular-import
# partial-init). Mirror this line for each future periodic-task module.
import app.wallet.reconcile  # noqa: E402, F401
