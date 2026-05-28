"""FastAPI app factory — Phase 1 scaffold + Phase 2 auth (AUTH-04, AUTH-08).

Lifespan:
  - configure_logging(settings) — structlog console/JSON renderer (D-24)
  - init_sentry(service="api", integrations=[FastApiIntegration, SqlalchemyIntegration]) — D-28

Middleware (order matters — outermost first):
  - RequestIdMiddleware (pure ASGI; D-26) — binds structlog contextvars FIRST
    so any later middleware / handler sees a request_id in logs.
  - SlowAPIMiddleware (Phase 2, D-14) — bridges slowapi's @limiter.limit
    decorators into the ASGI flow. Mounted AFTER RequestIdMiddleware so the
    rate-limit log line has request_id context.
  - CORSMiddleware (Phase 2, Pitfall 7) — single explicit origin so the
    cookie-credentials flow works in dev + prod.

Routes:
  - /healthz, /readyz (D-30) via app.routers.health
  - /_sentry-test — synthetic Sentry trigger (D-29); Phase 11 may gate or remove
  - /auth/* — player auth surface (Phase 2 — register, login, logout, verify,
    forgot-password, reset-password, request-verify-token, users/me)
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from app.auth.rate_limit import limiter
from app.auth.router import build_auth_routers
from app.bets.router import bets_router
from app.core.config import Settings
from app.core.logging import configure_logging
from app.core.sentry import init_sentry
from app.routers import health
from app.settlement.router import settlement_admin_router
from app.wallet.admin_router import wallet_admin_router
from app.wallet.router import wallet_router

# Read settings at module load — explicit Settings() per D-09; tests can patch this.
settings = Settings()


class RequestIdMiddleware:
    """Bind ``request_id`` / ``path`` / ``method`` / ``client_ip`` into structlog contextvars.

    Pure ASGI middleware (NOT ``BaseHTTPMiddleware``) — the latter runs endpoints
    in a task group that copies the context, so values bound here would be
    invisible inside route handlers. See FastAPI discussion #8632.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        structlog.contextvars.clear_contextvars()
        client = scope.get("client") or ("unknown", 0)
        structlog.contextvars.bind_contextvars(
            request_id=str(uuid.uuid4()),
            path=scope.get("path", "/"),
            method=scope.get("method", "GET"),
            client_ip=client[0],
        )
        try:
            await self.app(scope, receive, send)
        finally:
            structlog.contextvars.clear_contextvars()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Configure logging + Sentry at startup; nothing to tear down in Phase 1."""
    configure_logging(settings)
    init_sentry(
        service="api",
        settings=settings,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
    )
    yield


app = FastAPI(lifespan=lifespan, title="XPredict API")

# ---------------------------------------------------------------------------
# Middleware ordering — outermost first.
# ---------------------------------------------------------------------------
# Starlette runs the LAST registered middleware FIRST (outer-most). Order
# below is intentional:
#   1) CORSMiddleware (last registered → runs OUTERMOST) so preflight OPTIONS
#      and cookie-credentials flags are applied before any auth logic.
#   2) SlowAPIMiddleware — bridges @limiter.limit decorators to ASGI.
#   3) RequestIdMiddleware (registered FIRST → runs INNERMOST) so structlog
#      contextvars are bound right next to the route handler.
app.add_middleware(RequestIdMiddleware)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_BASE_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Rate-limit error handler — slowapi convention.
# ---------------------------------------------------------------------------
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_exceeded_handler(  # type: ignore[no-untyped-def]
    request, exc,
):
    """Generic 429 — never leak whether the email existed (T-02-08, T-02-10)."""
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please try again later."},
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
from app.admin.router import admin_crm_router  # noqa: E402
from app.markets.router import admin_market_router, public_market_router  # noqa: E402

app.include_router(health.router)
app.include_router(build_auth_routers())
app.include_router(admin_crm_router)
app.include_router(admin_market_router)
app.include_router(public_market_router)
app.include_router(wallet_admin_router)
app.include_router(wallet_router)
app.include_router(bets_router)
app.include_router(settlement_admin_router)


@app.api_route("/_sentry-test", methods=["GET", "HEAD"])
async def sentry_test() -> dict[str, str]:
    """Synthetic Sentry trigger — D-29. Dev-only; returns 403 in staging/prod."""
    if not settings.is_dev:
        raise HTTPException(status_code=403, detail="not available")
    raise RuntimeError("sentry test from api")
