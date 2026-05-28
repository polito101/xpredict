"""Auth router — dual FastAPIUsers instances + slowapi-decorated proxy routes (D-03, D-12).

Pattern: **Option A from Pitfall 1** — thin proxy routes own the
``@limiter.limit(...)`` stack for the four critical endpoints
(register, login, forgot-password, request-verify-token). They call
``UserManager`` methods directly. The fastapi-users-provided routers
handle the rest (verify, reset-password, users/me, logout).

Player surface (CookieTransport):
- POST /auth/register           — proxy (rate-limited; AUTH-01..02)
- POST /auth/login              — proxy (rate-limited; AUTH-04, AUTH-08)
- POST /auth/forgot-password    — proxy (rate-limited; AUTH-06, AUTH-08, T-02-10)
- POST /auth/request-verify-token — proxy (rate-limited; AUTH-08)
- POST /auth/verify             — fastapi-users (single-use; AUTH-03)
- POST /auth/reset-password     — fastapi-users (AUTH-06)
- POST /auth/logout             — fastapi-users (AUTH-05)
- GET  /auth/users/me           — fastapi-users (gated active+verified)

Admin surface (BearerTransport) — Plan 02-03 (D-03, AUTH-07):
- POST /admin/auth/login        — proxy (rate-limited; AUTH-07, AUTH-08)
- POST /admin/auth/logout       — proxy (revokes Bearer; T-02-36)

Both surfaces share the same ``User`` model, ``UserManager`` class, and
custom ``DatabaseStrategy`` — only the transport differs. See
``admin_router.py`` for the cross-surface isolation rationale.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users import FastAPIUsers, exceptions
from fastapi_users.authentication import (
    AuthenticationBackend,
    CookieTransport,
)
from pydantic import BaseModel, EmailStr
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.deps import get_user_manager
from app.auth.manager import UserManager
from app.auth.models import User
from app.auth.rate_limit import check_email_limit, get_remote_address, limiter
from app.auth.schemas import UserCreate, UserRead, UserUpdate
from app.auth.strategy import get_database_strategy
from app.core.audit.service import AuditService
from app.core.config import get_settings
from app.db.session import _get_session_maker

settings = get_settings()


# ----------------------------------------------------------------------
# Player surface (CookieTransport) — D-03, Pitfall 3 (cookie_secure)
# ----------------------------------------------------------------------
cookie_transport = CookieTransport(
    cookie_name="xpredict_session",
    cookie_max_age=settings.REFRESH_TOKEN_LIFETIME_SECONDS,
    cookie_httponly=True,
    cookie_secure=not settings.is_dev,       # False in dev, True in staging/prod
    cookie_samesite="lax",
    cookie_path="/",
)

player_backend = AuthenticationBackend(
    name="player-cookie",
    transport=cookie_transport,
    get_strategy=get_database_strategy,
)

fastapi_users_player = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [player_backend],
)

# Convenience deps — Pitfall 10 (is_verified gate on protected routes).
current_active_player = fastapi_users_player.current_user(active=True, verified=True)


# ----------------------------------------------------------------------
# Helper: get an audit session factory for proxy routes that bypass the
# fastapi-users-managed transaction (e.g. login proxy writes
# auth.session_started audit row in a fresh session).
# ----------------------------------------------------------------------
def _get_audit_session_factory() -> async_sessionmaker[AsyncSession]:
    return _get_session_maker()


# ----------------------------------------------------------------------
# Pydantic body schemas for proxy routes
# ----------------------------------------------------------------------
class _ForgotPasswordBody(BaseModel):
    email: EmailStr


class _RequestVerifyBody(BaseModel):
    email: EmailStr


# ----------------------------------------------------------------------
# Proxy router — owns the @limiter decorators (Pitfall 1 Option A)
# ----------------------------------------------------------------------
auth_proxy_router = APIRouter(prefix="/auth", tags=["auth"])


@auth_proxy_router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("5/minute", key_func=get_remote_address)
async def register_proxy(
    request: Request,
    response: Response,
    user_create: UserCreate,
    user_manager: Annotated[UserManager, Depends(get_user_manager)],
) -> Any:
    """Proxy POST /auth/register — IP-rate-limited + email-rate-limited."""
    # Per-email limit (manual inside body — see rate_limit.check_email_limit).
    check_email_limit(request, user_create.email)
    try:
        created = await user_manager.create(user_create, safe=True, request=request)
    except exceptions.UserAlreadyExists as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="REGISTER_USER_ALREADY_EXISTS",
        ) from exc
    except exceptions.InvalidPasswordException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "REGISTER_INVALID_PASSWORD",
                "reason": exc.reason,
            },
        ) from exc
    _ = response  # slowapi injects X-RateLimit-* headers via this object
    return UserRead.model_validate(created, from_attributes=True)


@auth_proxy_router.post("/login")
@limiter.limit("5/minute", key_func=get_remote_address)
async def login_proxy(
    request: Request,
    credentials: Annotated[OAuth2PasswordRequestForm, Depends()],
    user_manager: Annotated[UserManager, Depends(get_user_manager)],
) -> Response:
    """Proxy POST /auth/login — IP+email rate-limited; cookie issuance + audit."""
    check_email_limit(request, credentials.username)
    user = await user_manager.authenticate(credentials)
    if user is None or not user.is_active:
        # Pitfall 8 + T-02-11: fastapi-users authenticate already runs a
        # dummy hash on missing user, so timing variance is minimal.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LOGIN_BAD_CREDENTIALS",
        )

    # Phase 8 D-02 — ban enforcement at login. Valid credentials but a banned
    # account is 403 "Account suspended" (NOT 401/400 — the credentials are
    # correct, the account is suspended). No cookie is issued (T-08-02).
    user_manager.assert_not_banned(user)

    strategy = get_database_strategy()
    response = await player_backend.login(strategy, user)

    # Audit auth.session_started in an independent session (the request
    # transaction is already closed by the strategy's own commit).
    factory = _get_audit_session_factory()
    async with factory() as session:
        client_ip = request.client.host if request.client else None
        await AuditService.record(
            session,
            actor=f"user:{user.id}",
            event_type="auth.session_started",
            payload={"email": user.email},
            ip=client_ip,
        )
        await session.commit()
    return response


@auth_proxy_router.post(
    "/forgot-password",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("5/minute", key_func=get_remote_address)
async def forgot_password_proxy(
    request: Request,
    response: Response,
    body: _ForgotPasswordBody,
    user_manager: Annotated[UserManager, Depends(get_user_manager)],
) -> dict[str, str]:
    """Proxy POST /auth/forgot-password — 202 unconditionally (T-02-10)."""
    check_email_limit(request, body.email)
    try:
        user = await user_manager.get_by_email(body.email)
        await user_manager.forgot_password(user, request)
    except exceptions.UserNotExists:
        # Anti-pattern from RESEARCH line 920: must NOT branch on existence.
        pass
    _ = response
    return {"status": "accepted"}


@auth_proxy_router.post(
    "/request-verify-token",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("5/minute", key_func=get_remote_address)
async def request_verify_proxy(
    request: Request,
    response: Response,
    body: _RequestVerifyBody,
    user_manager: Annotated[UserManager, Depends(get_user_manager)],
) -> dict[str, str]:
    """Proxy POST /auth/request-verify-token — 202 unconditionally."""
    check_email_limit(request, body.email)
    try:
        user = await user_manager.get_by_email(body.email)
        await user_manager.request_verify(user, request)
    except (exceptions.UserNotExists, exceptions.UserAlreadyVerified):
        # No leak — same response shape regardless.
        pass
    _ = response
    return {"status": "accepted"}


_PROXY_OWNED_PATHS: set[str] = {
    "/login",
    "/register",
    "/forgot-password",
    "/request-verify-token",
}


def _strip_proxy_owned(fu_router: APIRouter) -> APIRouter:
    """Filter out routes whose path is owned by our proxy router.

    fastapi-users' ``get_auth_router`` provides /login + /logout, and
    ``get_reset_password_router`` provides /forgot-password + /reset-password.
    The proxy already owns /login + /forgot-password; mounting the
    fastapi-users router as-is would register duplicate route handlers
    with diverging behaviour (the proxy has the @limiter decorator, the
    fastapi-users route does not). Removing the duplicates here keeps the
    OpenAPI schema and route table clean.
    """
    fu_router.routes = [
        r for r in fu_router.routes
        if getattr(r, "path", None) not in _PROXY_OWNED_PATHS
    ]
    return fu_router


# ----------------------------------------------------------------------
# build_auth_routers — included in main.py
# ----------------------------------------------------------------------
def build_auth_routers() -> APIRouter:
    """Return a parent router containing all auth routes (player + admin)."""
    parent = APIRouter()

    # 1) Proxy router — owns rate-limited routes (register/login/forgot/
    #    request-verify-token).
    parent.include_router(auth_proxy_router)

    # 2) fastapi-users built-in routers — with the proxy-owned paths
    #    stripped so we don't register duplicate handlers.
    parent.include_router(
        _strip_proxy_owned(
            fastapi_users_player.get_auth_router(player_backend),
        ),
        prefix="/auth",
        tags=["auth"],
    )
    # Verify: POST /verify  (single-use; AUTH-03).  /request-verify-token
    # comes from this router too; proxy owns it.
    parent.include_router(
        _strip_proxy_owned(
            fastapi_users_player.get_verify_router(UserRead),
        ),
        prefix="/auth",
        tags=["auth"],
    )
    # Reset: POST /reset-password (proxy owns /forgot-password).
    parent.include_router(
        _strip_proxy_owned(
            fastapi_users_player.get_reset_password_router(),
        ),
        prefix="/auth",
        tags=["auth"],
    )
    # Users CRUD: GET /users/me etc. Pitfall 10 — require verification on
    # the protected user surface so unverified accounts can log in but cannot
    # access /auth/users/me.
    parent.include_router(
        fastapi_users_player.get_users_router(
            UserRead, UserUpdate, requires_verification=True,
        ),
        prefix="/auth/users",
        tags=["auth"],
    )

    # 3) Admin surface (Plan 02-03, D-03, AUTH-07). The admin proxy owns
    #    /admin/auth/login + /admin/auth/logout — both rate-limited /
    #    audit-aware. No additional fastapi-users router is mounted for
    #    the admin instance because admins are seeded via
    #    ``bin/create_admin.py`` (no register flow) and don't need
    #    email-verification or password-reset endpoints in v1.
    from app.auth.admin_router import admin_proxy_router  # local import — avoid circular

    parent.include_router(admin_proxy_router)
    return parent


# Suppress unused-import noise — these are intentionally exported.
__all__ = [
    "build_auth_routers",
    "cookie_transport",
    "current_active_player",
    "fastapi_users_player",
    "player_backend",
]


# Update is imported but used in router-internal helpers; explicit reference
# keeps the import alive for module-level sequence safety.
_ = update
