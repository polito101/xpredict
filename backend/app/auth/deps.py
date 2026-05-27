"""FastAPI dependency factories for auth.

Re-exports the dependencies that Phase 3+ will consume:
- ``get_user_db`` — produces ``SQLAlchemyUserDatabase(session, User)``
- ``get_email_service`` — singleton-ish ``EmailService`` factory
- ``get_user_manager`` — produces a ``UserManager`` wired to user_db + email
- ``current_active_player`` / ``current_active_admin`` — re-exported from router

The ``current_active_*`` symbols are bound at the bottom of ``router.py``
and re-exported here so consumers can:

    from app.auth.deps import current_active_player

without importing ``app.auth.router`` (which is FastAPI-app-scoped).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache
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
    """Yield a UserManager wired with the request user_db + shared email service."""
    yield UserManager(user_db, email_service=email_service)


__all__ = [
    "get_email_service",
    "get_user_db",
    "get_user_manager",
]
