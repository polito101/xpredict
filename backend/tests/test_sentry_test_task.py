"""Sentry synthetic-trigger Celery task test — D-29 / PLT-08 (worker surface)."""

from __future__ import annotations

import pytest

from app.celery_app import sentry_test_task


def test_sentry_test_task_raises() -> None:
    """Calling sentry_test_task() synchronously raises RuntimeError with the canonical msg."""
    with pytest.raises(RuntimeError, match="sentry test from worker"):
        sentry_test_task()
