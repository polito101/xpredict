"""Async session factory + FastAPI dependency (D-07, D-41).

Connection-pool sizing per D-41: ``pool_size=10, max_overflow=10, pool_pre_ping=True,
pool_recycle=3600``. No PgBouncer in v1 — when staging adds it, callers must remember
the ``SET LOCAL`` doctrine (PITFALLS.md #7); never session-level GUCs.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


@lru_cache(maxsize=1)
def _get_engine() -> AsyncEngine:
    """Lazy engine factory — avoids constructing a pool at module import time.

    This makes the module safe to import in test contexts (where Settings may not
    have the env vars set) and in Alembic env.py loading (which reads the same
    Settings but uses a sync engine).
    """
    settings = Settings()
    return create_async_engine(
        str(settings.DATABASE_URL),
        pool_size=10,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=settings.is_dev,
    )


@lru_cache(maxsize=1)
def _get_session_maker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        _get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an ``AsyncSession``.

    Sessions are NOT auto-committed; callers control transaction boundaries.
    ``AuditService.record()`` follows this contract — audit insert lives in the
    caller's tx so the underlying action + audit row commit atomically (D-21).
    """
    session_maker = _get_session_maker()
    async with session_maker() as session:
        yield session
