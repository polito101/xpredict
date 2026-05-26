"""pytest fixtures — testcontainers Postgres + fakeredis + FastAPI client.

Phase 1 Plan 01-01 shipped the lightweight fixtures (``fake_redis``,
``client``); Plan 01-03 extends the heavyweight ``engine`` fixture to run
``alembic upgrade head`` against the testcontainer Postgres so the
integration tests in ``tests/core/`` see the schema.

Crucially: the Postgres-touching fixtures are *lazy* — they only spawn
Docker when a test actually requests them. Tests that don't reference them
run with zero Docker dependency.

A session-level ``_test_env_setup`` autouse fixture seeds ``DATABASE_URL``,
``DATABASE_URL_SYNC``, and ``REDIS_URL`` env vars so ``Settings()`` can be
instantiated everywhere without bespoke per-test monkeypatch. Tests that
exercise validation errors (e.g., malformed URLs) override this with
explicit constructor args.
"""

from __future__ import annotations

import os
import warnings
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
    from testcontainers.postgres import PostgresContainer


# ---------------------------------------------------------------------------
# Environment seeding (runs at conftest IMPORT, before any test collection)
# ---------------------------------------------------------------------------
#
# Module-level seeding is required because ``app.celery_app`` (and any future
# module that instantiates ``Settings()`` at import time) is loaded during
# collection — before any pytest fixture runs. Setting env vars in a
# session-scoped fixture would be too late.
#
# Tests that need to verify Settings validation (e.g., malformed URL,
# extra-key ignore) pass explicit constructor args, so they don't rely on
# this default.

_DEFAULT_TEST_ENV: dict[str, str] = {
    "ENVIRONMENT": "dev",
    "DATABASE_URL": "postgresql+asyncpg://xpredict:xpredict@localhost:5432/xpredict",
    "DATABASE_URL_SYNC": "postgresql+psycopg2://xpredict:xpredict@localhost:5432/xpredict",
    "REDIS_URL": "redis://localhost:6379/0",
    "SENTRY_DSN": "",
    "LOG_LEVEL": "INFO",
}

for _k, _v in _DEFAULT_TEST_ENV.items():
    os.environ.setdefault(_k, _v)


# ---------------------------------------------------------------------------
# Lightweight fixtures (no Docker, used by Plan 01-01 tests)
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_redis() -> Generator[Any, None, None]:
    """Yield an in-memory ``fakeredis.aioredis.FakeRedis`` client."""
    import fakeredis.aioredis

    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    try:
        yield client
    finally:
        # FakeRedis cleanup is sync — no aclose() needed for in-memory state
        pass


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """FastAPI test client wired through httpx ASGITransport.

    ``raise_app_exceptions=False`` so that ``/_sentry-test`` (and any future
    route that intentionally raises) returns a real 500 response — Sentry's
    integration relies on FastAPI's ``ServerErrorMiddleware`` to convert the
    exception, and we want to exercise that path in the test.
    """
    import httpx

    from app.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Heavyweight fixtures (testcontainers Postgres) — used by Plan 01-03+
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    """Session-scoped Postgres 16 container.

    Marked LAZY: only starts when a test that actually depends on this
    fixture is collected. Plan 01-01 tests do NOT request it, so no Docker
    daemon is required to run the Wave-0 unit suite.
    """
    pytest.importorskip(
        "testcontainers",
        reason="testcontainers required for Postgres fixtures",
    )
    from testcontainers.postgres import PostgresContainer

    with warnings.catch_warnings():
        # testcontainers emits DeprecationWarnings on its internal HTTP probes.
        warnings.simplefilter("ignore", DeprecationWarning)
        with PostgresContainer("postgres:16-alpine") as pg:
            yield pg


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine(postgres_container: PostgresContainer) -> AsyncGenerator[AsyncEngine, None]:
    """Async engine bound to the testcontainer, with ``alembic upgrade head`` applied.

    The container's psycopg2 URL is rewritten to asyncpg for the app; the
    psycopg2 form is set in ``DATABASE_URL_SYNC`` so Alembic's sync engine
    can connect during upgrade. Both env vars are set BEFORE running
    ``alembic upgrade head`` so ``Settings()`` inside ``alembic/env.py``
    picks them up.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    from alembic import command
    from alembic.config import Config

    sync_url = postgres_container.get_connection_url()
    # testcontainers may emit psycopg2 or postgresql+psycopg2 — normalise to
    # the SQLAlchemy form Alembic expects.
    if "+psycopg2" not in sync_url:
        sync_url = sync_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    async_url = sync_url.replace("+psycopg2", "+asyncpg")

    # Override env vars BEFORE running alembic — env.py reads Settings() at
    # module import, so we must clobber the conftest defaults here.
    os.environ["DATABASE_URL"] = async_url
    os.environ["DATABASE_URL_SYNC"] = sync_url

    # Clear the lazy engine cache so subsequent `_get_engine()` calls pick
    # up the new env (defensive — pytest may have warmed the cache).
    try:
        from app.db.session import _get_engine, _get_session_maker

        _get_engine.cache_clear()
        _get_session_maker.cache_clear()
    except ImportError:  # pragma: no cover
        pass

    # Run alembic upgrade head against the container's psycopg2 URL.
    backend_root = Path(__file__).parent.parent
    alembic_cfg = Config(str(backend_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_root / "alembic"))
    command.upgrade(alembic_cfg, "head")

    eng = create_async_engine(async_url, pool_pre_ping=True)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def async_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Session-scoped ``AsyncSession`` wrapped in a transaction that rolls back.

    The outer transaction is opened once for the entire test session and rolled
    back at the end — every test sees a clean slate because writes are never
    committed to the real DB. Using ``scope="session"`` (not the default
    ``"function"``) prevents the fixture from being torn down and re-entered
    within the same event loop, which would cause asyncpg
    ``"Event loop is closed"`` errors under pytest-asyncio 0.25.

    For true per-test isolation use savepoints (``conn.begin_nested()``) inside
    individual tests that need it.
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            # Pass connection positionally — `bind=` was deprecated in
            # SQLAlchemy 2.0 and removed in 2.1 (WR-02).
            async with AsyncSession(conn, expire_on_commit=False) as session:
                yield session
        finally:
            await trans.rollback()
