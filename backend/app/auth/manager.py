"""UserManager with validate_password (AUTH-01) + four lifecycle hooks (AUTH-02, AUTH-06).

Researcher correction to CONTEXT D-06: EmailService is plain Python, NOT a
``BaseEmailSender`` protocol — it's injected via ``__init__``.

Hooks call EmailService inside try/except per Pitfall 5 (RESEARCH lines
1000-1014) — SMTP outage MUST NOT block the underlying auth state mutation.

``on_after_reset_password`` does BOTH the token_version bump AND the bulk
revoke per Pitfall 6 (RESEARCH lines 1019-1024) — belt-and-suspenders.

Audit writes use ``AuditService.record(session, ...)``. The manager opens its
own audit session via ``async_sessionmaker`` (same pattern as the Strategy)
to keep the audit row independent of the request transaction.

Note: there is NO ``on_after_login`` hook in fastapi-users — the
``auth.session_started`` audit row is written by the proxy login route in
``router.py``, not here.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

import structlog
from fastapi_users import BaseUserManager, UUIDIDMixin
from fastapi_users.exceptions import InvalidPasswordException
from fastapi_users.password import PasswordHelperProtocol
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.requests import Request

from app.auth.email import EmailService
from app.auth.models import RefreshToken, User
from app.auth.schemas import UserCreate
from app.core.audit.service import AuditService
from app.core.config import get_settings
from app.db.session import _get_session_maker

logger = structlog.get_logger(__name__)


class UserManager(UUIDIDMixin, BaseUserManager[User, UUID]):
    """Player + admin user manager — owns lifecycle hooks + audit + email."""

    reset_password_token_secret = get_settings().SECRET_KEY
    verification_token_secret = get_settings().SECRET_KEY

    def __init__(
        self,
        user_db: Any,
        password_helper: PasswordHelperProtocol | None = None,
        *,
        email_service: EmailService | None = None,
        audit_session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        super().__init__(user_db, password_helper)
        self.email_service = email_service or EmailService()
        self.audit_session_factory = audit_session_factory or _get_session_maker()

    # ------------------------------------------------------------------
    # AUTH-01 — server-side password strength validation
    # ------------------------------------------------------------------
    async def validate_password(  # type: ignore[override]
        self,
        password: str,
        user: User | UserCreate,
    ) -> None:
        """Enforce 12+ chars, upper/lower/digit, no email substring."""
        if len(password) < 12:
            raise InvalidPasswordException(
                reason="Password must be at least 12 characters."
            )
        if not re.search(r"[A-Z]", password):
            raise InvalidPasswordException(
                reason="Password must contain an uppercase letter."
            )
        if not re.search(r"[a-z]", password):
            raise InvalidPasswordException(
                reason="Password must contain a lowercase letter."
            )
        if not re.search(r"\d", password):
            raise InvalidPasswordException(
                reason="Password must contain a digit."
            )
        # Email-substring rule — applies to both UserCreate (register) AND
        # User (password change), since BaseUserManager passes whichever is
        # available.
        email = getattr(user, "email", None)
        if email and email.lower() in password.lower():
            raise InvalidPasswordException(
                reason="Password must not contain your email."
            )

    # ------------------------------------------------------------------
    # AUTH-02 — register / request_verify hook chain
    # ------------------------------------------------------------------
    async def on_after_register(
        self, user: User, request: Request | None = None
    ) -> None:
        """Audit + trigger verification email (Pitfall 5 — best-effort SMTP)."""
        await self._audit(
            actor=f"user:{user.id}",
            event_type="auth.guest_created",
            payload={"email": user.email},
            request=request,
        )
        try:
            await self.request_verify(user, request)
        except Exception:
            logger.exception(
                "verification_email_send_failed",
                user_id=str(user.id),
            )
            # Pitfall 5: do NOT re-raise — registration succeeds even on
            # SMTP outage. The user can retry via /auth/request-verify-token.

    async def on_after_request_verify(
        self, user: User, token: str, request: Request | None = None
    ) -> None:
        """Send verification email.

        Called from on_after_register or POST /auth/request-verify-token.
        """
        try:
            await self.email_service.send_verification_email(
                to=user.email, token=token
            )
        except Exception:
            logger.exception(
                "verification_email_send_failed",
                user_id=str(user.id),
            )

    # ------------------------------------------------------------------
    # AUTH-03 — verify hook (audit only; user.is_verified=True is set by
    # fastapi-users itself)
    # ------------------------------------------------------------------
    async def on_after_verify(
        self, user: User, request: Request | None = None
    ) -> None:
        await self._audit(
            actor=f"user:{user.id}",
            event_type="auth.email_verified",
            payload={"email": user.email},
            request=request,
        )

    # ------------------------------------------------------------------
    # AUTH-06 — forgot-password (audit + email)
    # ------------------------------------------------------------------
    async def on_after_forgot_password(
        self, user: User, token: str, request: Request | None = None
    ) -> None:
        await self._audit(
            actor=f"user:{user.id}",
            event_type="auth.password_reset_requested",
            payload={"email": user.email},
            request=request,
        )
        try:
            await self.email_service.send_reset_password_email(
                to=user.email, token=token
            )
        except Exception:
            logger.exception(
                "reset_password_email_send_failed",
                user_id=str(user.id),
            )

    # ------------------------------------------------------------------
    # AUTH-06 — reset-password completion: belt-and-suspenders Pitfall 6
    # ------------------------------------------------------------------
    async def on_after_reset_password(
        self, user: User, request: Request | None = None
    ) -> None:
        """Bump token_version AND revoke all active refresh tokens (Pitfall 6)."""
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        async with self.audit_session_factory() as session:
            # Bump token_version (AUTH-06 invalidation gate)
            await session.execute(
                update(User)
                .where(User.id == user.id)  # type: ignore[arg-type]
                .values(token_version=User.token_version + 1)
            )
            # Bulk revoke all currently-active tokens (clean DB state)
            await session.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.user_id == user.id,
                    RefreshToken.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            # Audit row in the same tx as the mutations
            await AuditService.record(
                session,
                actor=f"user:{user.id}",
                event_type="auth.password_reset_completed",
                payload={"email": user.email},
            )
            await session.commit()

    # ------------------------------------------------------------------
    # Internal: open an independent audit session and commit one row.
    # ------------------------------------------------------------------
    async def _audit(
        self,
        *,
        actor: str,
        event_type: str,
        payload: dict[str, Any],
        request: Request | None,
    ) -> None:
        ip = self._client_ip(request)
        async with self.audit_session_factory() as session:
            await AuditService.record(
                session,
                actor=actor,
                event_type=event_type,
                payload=payload,
                ip=ip,
            )
            await session.commit()

    @staticmethod
    def _client_ip(request: Request | None) -> str | None:
        if request is None:
            return None
        client = request.client
        return client.host if client else None


__all__ = ["UserManager"]
