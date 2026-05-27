"""FastAPI dependency factories for auth.

Re-exports the dependencies that Phase 3+ will consume:
- ``get_user_db`` — produces ``SQLAlchemyUserDatabase(session, User)``
- ``get_email_service`` — singleton-ish ``EmailService`` factory
- ``get_user_manager`` — produces a ``UserManager`` wired to user_db + email
- ``current_active_player`` — re-exported from ``router.py`` (Plan 02-02)
- ``current_active_admin`` — re-exported from ``admin_router.py`` (Plan 02-03)

The ``current_active_*`` symbols are bound at the bottom of ``router.py``
and ``admin_router.py`` and re-exported here so consumers can:

    from app.auth.deps import current_active_player, current_active_admin

without importing the router modules (which are FastAPI-app-scoped).
Re-exports use module-level ``__getattr__`` to break the import cycle
(``admin_router`` imports ``get_user_manager`` from this module).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Any
from uuid import UUID

from fastapi import Depends
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.email import EmailService
from app.auth.manager import UserManager
from app.auth.models import User
from app.db.session import get_async_session


async def get_user_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase[User, UUID], None]:
    """Yield the fastapi-users SQLAlchemy adapter bound to the request session."""
    yield SQLAlchemyUserDatabase(session, User)


@lru_cache(maxsize=1)
def _get_email_service_singleton() -> EmailService:
    return EmailService()


def get_email_service() -> EmailService:
    """Return the shared ``EmailService`` instance.

    Cached because constructing it sets ``resend.api_key`` (a global) and
    we want to avoid re-setting on every request.
    """
    return _get_email_service_singleton()


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase[User, UUID] = Depends(get_user_db),
    email_service: EmailService = Depends(get_email_service),
) -> AsyncGenerator[UserManager, None]:
    """Yield a UserManager wired with the request user_db + shared email service.

    SAFETY NOTE — this dependency is only safe when called from a
    fastapi-users-managed route (register, login, verify, reset-password, etc.)
    or from routes that explicitly commit the session themselves.

    Rationale: ``UserManager`` does not hold its own session; all DB mutations
    go through the request-scoped session from ``get_user_db``.
    ``get_user_manager`` does NOT call ``session.commit()`` at teardown — it
    relies entirely on fastapi-users' internal commit logic.

    If you add a CUSTOM route that uses ``Depends(get_user_manager)`` and
    directly mutates the user object (e.g. ``user.is_verified = True`` without
    going through a fastapi-users method), you MUST call
    ``await session.commit()`` inside that route before returning, otherwise
    the mutation will be silently lost when the session closes.
    """
    yield UserManager(user_db, email_service=email_service)


def __getattr__(name: str) -> Any:
    """Lazy re-exports — break import cycle with admin_router / router."""
    if name == "current_active_admin":
        from app.auth.admin_router import current_active_admin

        return current_active_admin
    if name == "current_active_player":
        from app.auth.router import current_active_player

        return current_active_player
    raise AttributeError(f"module 'app.auth.deps' has no attribute {name!r}")


# ``current_active_admin`` + ``current_active_player`` are resolved by
# the module-level ``__getattr__`` above (lazy import to break cycle).
# Ruff sees them as undefined in ``__all__`` (F822); the ``noqa`` keeps
# the lint clean. The names ARE importable at call time, as the unit
# tests assert.
__all__ = [
    "current_active_admin",  # noqa: F822 — lazy __getattr__
    "current_active_player",  # noqa: F822 — lazy __getattr__
    "get_email_service",
    "get_user_db",
    "get_user_manager",
]
