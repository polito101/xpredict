"""Shared fixtures for the admin CRM integration tests (Phase 8, Plan 08-01).

Mirrors ``tests/markets/conftest.py``: a rate-limit reset autouse fixture so the
5/min login cap on ``/admin/auth/login`` never bleeds across tests (every test
logs the admin in to mint a fresh Bearer).
"""

from __future__ import annotations

import contextlib

import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limit_storage():
    """Reset the slowapi limiter between tests so admin login is never throttled."""
    from app.auth.rate_limit import limiter

    try:
        limiter._limiter.reset()
    except Exception:
        with contextlib.suppress(Exception):
            limiter._storage.reset()
    yield
