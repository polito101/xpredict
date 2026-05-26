"""structlog configuration (D-23, D-24, D-25, D-26).

One ``configure_logging(settings)`` call at process start (FastAPI lifespan,
Celery worker_process_init, Celery beat_init). After that, every ``structlog
.get_logger()`` returns a logger that:

  - merges contextvars (set by RequestIdMiddleware per request, by Celery
    task_prerun signal per task) so every line carries request_id/task_id;
  - renders as colored Console in dev (``settings.is_dev``), JSON otherwise;
  - scrubs sensitive keys (``SCRUB_KEYS``) on every event — D-25 preempts
    Phase 2's ``session_signing_key``, ``admin_token``, and ``xp_session``
    cookies before Phase 2 introduces them.

The scrub list is the parallel defense for ``Settings(extra="ignore")``
(Pitfall 3) — if a secret slips into a log call via ``logger.info(..., x=y)``,
it's masked before it leaves the process.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

from app.core.config import Settings

SCRUB_KEYS: set[str] = {
    "password",
    "password_hash",
    "session_signing_key",
    "admin_token",
    "sentry_dsn",
    "api_key",
    "secret",
    "xp_session",
}


def _scrub_recursive(obj: Any) -> Any:
    """Recursively walk ``obj`` and replace values for sensitive keys with ``***``.

    Handles dicts (arbitrary depth), lists, and scalars. Called by
    ``scrub_secrets`` so the protection applies to both top-level and nested
    structured log fields (e.g. ``logger.info("auth", payload={"password": "x"})``).
    """
    if isinstance(obj, dict):
        return {
            k: "***" if k.lower() in SCRUB_KEYS else _scrub_recursive(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_scrub_recursive(item) for item in obj]
    return obj


def scrub_secrets(
    _logger: Any,
    _name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """structlog processor — replace values for sensitive keys with ``***``.

    Walks the event dict recursively so nested dicts (e.g.
    ``payload={"password": "x"}``) are scrubbed in addition to top-level keys.
    """
    scrubbed = _scrub_recursive(dict(event_dict))
    event_dict.clear()
    event_dict.update(scrubbed)
    return event_dict


def configure_logging(settings: Settings) -> None:
    """Configure structlog + stdlib root logger once at startup.

    Idempotent in practice (structlog.configure replaces previous config), but
    call this exactly once: in FastAPI lifespan, and in each Celery signal
    handler that needs it (worker_process_init / beat_init). Test code can call
    it freely.
    """
    # Capture stdlib logger output (FastAPI, uvicorn, Celery)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=settings.LOG_LEVEL,
    )

    renderer: Any
    if settings.is_dev:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            scrub_secrets,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.LOG_LEVEL)
        ),
        cache_logger_on_first_use=True,
    )
