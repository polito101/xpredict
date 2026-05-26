"""Sentry SDK init helpers (D-27, D-28).

One project per environment (xpredict-dev / xpredict-staging / xpredict-prod);
every event tagged ``service=api|worker|beat|frontend``. Callers pass their own
integrations:

  - FastAPI: ``[FastApiIntegration(), SqlalchemyIntegration()]`` (see main.py)
  - Celery worker/beat: ``[CeleryIntegration(), SqlalchemyIntegration()]``
    (see celery_app.py)

Pitfall 5: init MUST happen in the worker_process_init / beat_init signals
(not at module-level) so Sentry SDK process-global state is the right one for
each Celery process. Otherwise events leak across services.
"""

from __future__ import annotations

from typing import Any

import sentry_sdk

from app.core.config import Settings


def init_sentry(
    service: str,
    settings: Settings,
    integrations: list[Any] | None = None,
) -> None:
    """Initialise Sentry SDK and tag this process with ``service=<name>``.

    No-op when ``settings.SENTRY_DSN`` is None — tests and local dev without a
    DSN run unbothered. Callers in FastAPI lifespan and Celery
    worker_process_init / beat_init signals each pass their own ``service``
    name and integration list.
    """
    if not settings.SENTRY_DSN:
        return
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        integrations=integrations or [],
        send_default_pii=False,
    )
    sentry_sdk.set_tag("service", service)
