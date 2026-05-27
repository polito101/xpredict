"""Admin authentication surface — BearerTransport + cross-surface isolation (D-03, AUTH-07).

Phase 2 dual-backend pattern locked by CONTEXT D-03: a SEPARATE
``FastAPIUsers`` instance from the player surface — same ``User`` model,
same ``UserManager`` class, same custom ``DatabaseStrategy``, but
``BearerTransport`` instead of ``CookieTransport``.

# Anti-pattern locked: NEVER reuse one FastAPIUsers instance with
# ``[cookie, bearer]`` (RESEARCH §"Anti-Patterns" line 917, verified via
# fastapi-users discussion #989). Doing so would make a player cookie
# satisfy ``current_user`` on /admin/* endpoints, defeating AUTH-07.

# Cross-surface isolation (T-02-25):
# - ``fastapi_users_admin`` only parses ``Authorization: Bearer ...``
#   (never a cookie); admin Bearer can NOT authenticate /auth/users/me.
# - ``fastapi_users_player`` only parses cookies (never a Bearer header);
#   player cookies can NOT authenticate /admin/*.
# Two FastAPIUsers instances + two transports = hard wall.

# AUTH-07 defense-in-depth (T-02-26):
# Even with the right transport, a non-admin user must NEVER receive an
# admin Bearer. The login proxy enforces ``user.is_superuser`` BEFORE
# minting the Bearer; non-admins get an identical 401 (no enumeration).

# Rate limiting (AUTH-08, T-02-27):
# /admin/auth/login inherits the same 5/min per-IP AND per-email caps
# as the player surface. Same slowapi decorator + same check_email_limit
# helper. The 429 handler in main.py serves a generic body — admin
# enumeration is just as forbidden as player enumeration.

# Audit (T-02-30, taxonomy line 723-724 of PATTERNS):
# - ``auth.admin_login_started`` on success
# - ``auth.admin_login_failed`` on failure (unknown email OR wrong password
#   OR non-superuser-with-correct-credentials — all indistinguishable to
#   the caller; the audit row captures the distinction internally)

# Logout (T-02-36):
# /admin/auth/logout is a thin proxy that calls ``strategy.destroy_token``
# directly on the presented Bearer. The same DatabaseStrategy that the
# player surface uses; the row's ``revoked_at`` is set; the test
# ``test_admin_bearer_revocation`` asserts the next request returns 401.

# Note on ``from __future__ import annotations``:
# Removed intentionally — Python 3.13 + FastAPI's ``inspect.signature``
# dependency resolver breaks when type annotations become forward-ref
# strings (same Plan 02-02 D-C / Deviation #1 issue). ``Annotated[T,
# Depends(...)]`` requires runtime-evaluable types.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi_users import FastAPIUsers
from fastapi_users.authentication import AuthenticationBackend, BearerTransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.deps import get_user_manager
from app.auth.manager import UserManager
from app.auth.models import User
from app.auth.rate_limit import check_email_limit, get_remote_address, limiter
from app.auth.strategy import DatabaseStrategy, get_database_strategy
from app.core.audit.service import AuditService
from app.db.session import _get_session_maker

# ----------------------------------------------------------------------
# Admin transport + backend + FastAPIUsers instance (D-03)
# ----------------------------------------------------------------------
# tokenUrl is documented to the OpenAPI consumer; the actual login route
# is our rate-limited proxy at the same path (see ``admin_login_proxy``).
bearer_transport = BearerTransport(tokenUrl="/admin/auth/login")

admin_backend = AuthenticationBackend(
    name="admin-bearer",
    transport=bearer_transport,
    # SAME strategy class as the player surface — only the transport
    # differs. Refresh-token rotation + reuse detection + token_version
    # gate all apply identically to admin Bearers (AUTH-09 admin scope).
    get_strategy=get_database_strategy,
)

fastapi_users_admin = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [admin_backend],
)

# AUTH-07: every /admin/* endpoint (Phase 4+) takes this Depends.
current_active_admin = fastapi_users_admin.current_user(
    active=True,
    superuser=True,
)


# ----------------------------------------------------------------------
# OAuth2 scheme reader for /admin/auth/logout — extracts the Bearer token
# from the Authorization header so we can call strategy.destroy_token.
# ----------------------------------------------------------------------
_oauth2_bearer_scheme = OAuth2PasswordBearer(
    tokenUrl="/admin/auth/login",
    auto_error=False,
)


# ----------------------------------------------------------------------
# Helper: independent audit session (same pattern as router.py login)
# ----------------------------------------------------------------------
def _get_audit_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the module-level sessionmaker for audit writes.

    Audit rows are written in an independent transaction so a strategy
    commit (token write) doesn't accidentally terminate the audit row's
    transaction or vice-versa (Pitfall 9 doctrine).
    """
    return _get_session_maker()


# ----------------------------------------------------------------------
# Admin proxy router — owns the @limiter decorators (Pitfall 1 Option A)
# ----------------------------------------------------------------------
admin_proxy_router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])


@admin_proxy_router.post("/login")
@limiter.limit("5/minute", key_func=get_remote_address)
async def admin_login_proxy(
    request: Request,
    credentials: Annotated[OAuth2PasswordRequestForm, Depends()],
    user_manager: Annotated[UserManager, Depends(get_user_manager)],
) -> Any:
    """Proxy POST /admin/auth/login — IP+email rate-limited; Bearer + audit.

    Returns OAuth2 token JSON ``{access_token, token_type}`` (NO Set-Cookie).
    Returns identical 401 for all failure modes:
    - unknown email
    - wrong password
    - correct credentials but ``is_superuser=False`` (T-02-26 / ROADMAP SC#5)
    """
    # Per-email limit (manual inside body — slowapi key_func can't read
    # async form body). Same pattern as the player login proxy.
    check_email_limit(request, credentials.username)

    user = await user_manager.authenticate(credentials)

    # Defense-in-depth: BOTH "user is None" AND "is_superuser=False" map
    # to the same audit event + same 401 response. The auth.admin_login_failed
    # event captures internally which arm fired (via the payload's
    # ``reason`` field), but the API surface is uniform — no enumeration.
    if user is None or not user.is_active or not user.is_superuser:
        await _audit_admin_login_failed(
            request=request,
            email=credentials.username,
            user=user,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Mint the Bearer via the strategy. ``admin_backend.login`` calls
    # ``strategy.write_token`` + wraps in the transport's
    # ``get_login_response`` → returns a Starlette JSONResponse with the
    # OAuth2 ``{access_token, token_type:'bearer'}`` body and NO Set-Cookie.
    strategy = get_database_strategy()
    response = await admin_backend.login(strategy, user)

    # Audit auth.admin_login_started in an independent session.
    factory = _get_audit_session_factory()
    async with factory() as session:
        client_ip = request.client.host if request.client else None
        await AuditService.record(
            session,
            actor=f"user:{user.id}",
            event_type="auth.admin_login_started",
            payload={"email": user.email},
            ip=client_ip,
        )
        await session.commit()

    return response


@admin_proxy_router.post("/logout")
async def admin_logout_proxy(
    request: Request,
    token: Annotated[str | None, Depends(_oauth2_bearer_scheme)],
    user_manager: Annotated[UserManager, Depends(get_user_manager)],
) -> Response:
    """Proxy POST /admin/auth/logout — revokes the presented Bearer (T-02-36).

    Calls ``strategy.destroy_token`` which UPDATEs the refresh_tokens row
    with ``revoked_at = NOW()``. A subsequent request with the same Bearer
    will fail authentication (the test asserts). Returns 204 No Content;
    idempotent (any missing/expired/already-revoked token also yields 204).
    """
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    strategy = get_database_strategy()
    user = await strategy.read_token(token, user_manager)
    if user is None:
        # No row OR already revoked OR expired — return 204 either way
        # (idempotent logout is the canonical fastapi-users behaviour).
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    await strategy.destroy_token(token, user)

    # Audit auth.session_revoked (taxonomy reuses the existing event;
    # admin/player distinction is captured by the actor prefix and surface).
    factory = _get_audit_session_factory()
    async with factory() as session:
        client_ip = request.client.host if request.client else None
        await AuditService.record(
            session,
            actor=f"user:{user.id}",
            event_type="auth.session_revoked",
            payload={"email": user.email, "surface": "admin"},
            ip=client_ip,
        )
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ----------------------------------------------------------------------
# Audit helper — auth.admin_login_failed
# ----------------------------------------------------------------------
async def _audit_admin_login_failed(
    *,
    request: Request,
    email: str,
    user: User | None,
) -> None:
    """Record auth.admin_login_failed with internal reason classification.

    The API surface returns identical 401 for all three failure modes:
    - ``unknown_email``: ``user is None``
    - ``inactive``: ``user is not None and not user.is_active``
    - ``not_superuser``: ``user is not None and user.is_active and
      not user.is_superuser``

    The audit row captures which arm fired (via ``payload.reason``) for
    internal forensics. The CALLER cannot tell which (no enumeration).
    """
    if user is None:
        reason = "unknown_email"
        actor = f"unknown:{email.strip().lower()}"
    elif not user.is_active:
        reason = "inactive"
        actor = f"user:{user.id}"
    elif not user.is_superuser:
        reason = "not_superuser"
        actor = f"user:{user.id}"
    else:
        # Shouldn't reach here — the caller only invokes this on failure
        # paths — but be defensive.
        reason = "unknown"
        actor = f"user:{user.id}"

    factory = _get_audit_session_factory()
    async with factory() as session:
        client_ip = request.client.host if request.client else None
        await AuditService.record(
            session,
            actor=actor,
            event_type="auth.admin_login_failed",
            payload={"email": email, "reason": reason},
            ip=client_ip,
        )
        await session.commit()


# ----------------------------------------------------------------------
# Public exports
# ----------------------------------------------------------------------
__all__ = [
    "admin_backend",
    "admin_proxy_router",
    "bearer_transport",
    "current_active_admin",
    "fastapi_users_admin",
]


# Silence unused-import warnings for re-exports that downstream modules
# (e.g. router.py) consume.
_ = DatabaseStrategy
