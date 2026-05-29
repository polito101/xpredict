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
from fastapi_users import BaseUserManager, UUIDIDMixin, exceptions
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
from app.wallet.service import WalletService

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
    # WAL-01 / SC#1 — register creates the user + wallet in ONE transaction
    # ------------------------------------------------------------------
    async def create(  # type: ignore[override]
        self,
        user_create: UserCreate,
        safe: bool = False,
        request: Request | None = None,
    ) -> User:
        """Create a user AND its ``user_wallet`` account in a single transaction.

        WHY this override exists (RESEARCH SC#1, Pitfall 1): the stock
        ``SQLAlchemyUserDatabase.create()`` calls ``session.commit()`` BEFORE
        ``BaseUserManager.create()`` invokes ``on_after_register``. That means
        the existing ``on_after_register`` hook CANNOT host same-transaction
        work — by the time it runs the user row is already committed, so a
        wallet created there would land in a SEPARATE transaction and a wallet
        failure would leave a committed user with no wallet (an orphan).

        The fix (RESEARCH Option A — minimal blast radius, stays inside the
        already-customized ``UserManager``): re-implement ``create()`` to
        co-insert the wallet on the adapter's OWN session between the user
        INSERT and a SINGLE ``commit()``. ``WalletService.create_wallet`` adds +
        flushes the wallet but MUST NEVER commit (its caller-owned-transaction
        contract, mirroring ``AuditService.record``) — this method owns the one
        commit, so user + wallet land atomically (SC#1 / WAL-01).

        Behaviour preserved vs. the stock path: ``validate_password`` runs
        first, ``UserAlreadyExists`` is raised on a duplicate email, the
        ``safe`` flag still gates ``create_update_dict`` vs.
        ``create_update_dict_superuser``, and ``on_after_register`` still fires
        (audit + best-effort verification email) AFTER the single commit.
        """
        await self.validate_password(user_create.password, user_create)

        existing_user = await self.user_db.get_by_email(user_create.email)
        if existing_user is not None:
            raise exceptions.UserAlreadyExists()

        user_dict = (
            user_create.create_update_dict()  # type: ignore[no-untyped-call]
            if safe
            else user_create.create_update_dict_superuser()  # type: ignore[no-untyped-call]
        )
        password = user_dict.pop("password")
        user_dict["hashed_password"] = self.password_helper.hash(password)

        # Use the SAME session the user_db adapter holds, and do NOT let the
        # stock adapter commit early — we own the single commit below so the
        # user row and the wallet row land in ONE transaction (SC#1).
        session: AsyncSession = self.user_db.session  # type: ignore[attr-defined]
        user: User = self.user_db.user_table(**user_dict)  # type: ignore[attr-defined]
        session.add(user)
        await session.flush()  # user.id is now populated, NOT yet committed

        # Co-insert the wallet on the SAME session (add + flush only — the
        # service never commits; that is this method's job).
        await WalletService.create_wallet(session, user=user)

        await session.commit()  # ONE transaction → user + wallet commit atomically
        await session.refresh(user)

        await self.on_after_register(user, request)
        return user

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
            raise InvalidPasswordException(reason="Password must be at least 12 characters.")
        if not re.search(r"[A-Z]", password):
            raise InvalidPasswordException(reason="Password must contain an uppercase letter.")
        if not re.search(r"[a-z]", password):
            raise InvalidPasswordException(reason="Password must contain a lowercase letter.")
        if not re.search(r"\d", password):
            raise InvalidPasswordException(reason="Password must contain a digit.")
        # Email-substring rule — applies to both UserCreate (register) AND
        # User (password change), since BaseUserManager passes whichever is
        # available. We check BOTH the full address and the local part, so
        # ``Subtest-Word-1234`` is rejected when the email is
        # ``subtest@example.com``.
        email = getattr(user, "email", None)
        if email:
            password_lc = password.lower()
            email_lc = email.lower()
            local_part = email_lc.split("@", 1)[0]
            if email_lc in password_lc or (local_part and local_part in password_lc):
                raise InvalidPasswordException(reason="Password must not contain your email.")

    # ------------------------------------------------------------------
    # AUTH-02 — register / request_verify hook chain
    # ------------------------------------------------------------------
    async def on_after_register(self, user: User, request: Request | None = None) -> None:
        """Audit + trigger verification email (Pitfall 5 — best-effort SMTP)."""
        await self._audit(
            actor=f"user:{user.id}",
            event_type="auth.guest_created",
            payload={"email": user.email},
            request=request,
        )
        try:
            await self.request_verify(user, request)
        except Exception as exc:
            logger.error(
                "verification_email_send_failed",
                user_id=str(user.id),
                error_type=type(exc).__name__,
                error=str(exc)[:200],
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
            await self.email_service.send_verification_email(to=user.email, token=token)
        except Exception as exc:
            logger.error(
                "verification_email_send_failed",
                user_id=str(user.id),
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )

    # ------------------------------------------------------------------
    # AUTH-03 — verify hook (audit only; user.is_verified=True is set by
    # fastapi-users itself)
    # ------------------------------------------------------------------
    async def on_after_verify(self, user: User, request: Request | None = None) -> None:
        await self._audit(
            actor=f"user:{user.id}",
            event_type="auth.email_verified",
            payload={"email": user.email},
            request=request,
        )
        # Phase 5 SC#4 / WAL-02 — grant the one-time sign-up bonus on verification.
        # ``is_verified=True`` is ALREADY committed by fastapi-users before this
        # hook runs, so a bonus failure MUST NOT propagate (verification stands).
        # The grant is idempotent (key ``bonus:{user.id}``), so a retry — or an
        # admin recharge — recovers safely and never double-credits.
        try:
            async with self.audit_session_factory() as session:
                await WalletService.grant_signup_bonus(
                    session,
                    user_id=user.id,
                    amount=get_settings().SIGNUP_BONUS_AMOUNT,
                )
        except Exception as exc:
            logger.error(
                "signup_bonus_grant_failed",
                user_id=str(user.id),
                error_type=type(exc).__name__,
                error=str(exc)[:200],
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
            await self.email_service.send_reset_password_email(to=user.email, token=token)
        except Exception as exc:
            logger.error(
                "reset_password_email_send_failed",
                user_id=str(user.id),
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )

    # ------------------------------------------------------------------
    # AUTH-06 — reset-password completion: belt-and-suspenders Pitfall 6
    # ------------------------------------------------------------------
    async def on_after_reset_password(self, user: User, request: Request | None = None) -> None:
        """Bump token_version AND revoke all active refresh tokens (Pitfall 6).

        Uses a CAS (check-and-set) WHERE clause to avoid a lost-update race
        with the fastapi-users request session that concurrently writes
        hashed_password.  If token_version was already bumped by a concurrent
        request (rowcount == 0), we log a warning and continue — the DB row
        already has the correct post-bump value.
        """
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        async with self.audit_session_factory() as session:
            # CAS bump: only update the row whose token_version still matches
            # the value we read.  This prevents a second concurrent reset from
            # silently overwriting a newer version back to the old value + 1.
            result = await session.execute(
                update(User)
                .where(
                    User.id == user.id,  # type: ignore[arg-type]
                    User.token_version == user.token_version,
                )
                .values(token_version=User.token_version + 1)
                .returning(User.token_version)
            )
            if result.rowcount == 0:  # type: ignore[attr-defined]
                # Concurrent reset already bumped the version — the DB is in
                # the correct state; log for observability but do not re-bump.
                logger.warning(
                    "token_version_cas_missed",
                    user_id=str(user.id),
                    observed_version=user.token_version,
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
