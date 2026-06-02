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

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sentry_sdk
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
from app.realtime.manager import manager
from app.realtime.subscriber import redis_subscriber
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


def _subscriber_done_callback(task: asyncio.Task[None]) -> None:
    """Surface an UNEXPECTED subscriber exit to logs + Sentry (WR-03).

    ``redis_subscriber`` reconnects internally, so the only expected way it ends
    is cancellation on shutdown. Any other completion (a bug, or an exception the
    reconnect loop didn't catch) means live updates have silently stopped for
    this worker — make that loud instead of invisible. Guarded against the normal
    cancelled-on-shutdown path.
    """
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        log = structlog.get_logger()
        log.error("realtime.subscriber_exited", exc_info=exc)
        sentry_sdk.capture_exception(exc)
    else:
        structlog.get_logger().error("realtime.subscriber_exited_unexpectedly")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Configure logging + Sentry at startup; run the WS price subscriber.

    Phase 9 (MKT-04): a single ``redis_subscriber`` task per worker process is
    started here (lifespan runs once per uvicorn worker → per-worker subscriber,
    which is what makes multi-worker correct) and cancelled in ``finally`` so it
    never leaks on reload (09-RESEARCH Pitfall 4). A done-callback surfaces an
    unexpected exit to Sentry/logs (WR-03) — the task itself reconnects on a
    Redis blip, so a completion that is NOT a shutdown cancellation is a defect.
    """
    configure_logging(settings)
    init_sentry(
        service="api",
        settings=settings,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
    )
    task = asyncio.create_task(redis_subscriber(manager, str(settings.REDIS_URL)))
    task.add_done_callback(_subscriber_done_callback)
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


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
    request,
    exc,
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
from app.admin.export_router import admin_export_router  # noqa: E402
from app.admin.kpi_router import kpi_router  # noqa: E402
from app.admin.router import admin_crm_router  # noqa: E402
from app.branding.admin_router import tenant_config_admin_router  # noqa: E402
from app.branding.router import branding_router  # noqa: E402
from app.core.audit.router import audit_admin_router  # noqa: E402
from app.markets.router import admin_market_router, public_market_router  # noqa: E402
from app.realtime.router import realtime_router  # noqa: E402

app.include_router(health.router)
app.include_router(build_auth_routers())
app.include_router(admin_crm_router)
app.include_router(admin_export_router)
app.include_router(kpi_router)
app.include_router(audit_admin_router)
app.include_router(admin_market_router)
app.include_router(tenant_config_admin_router)
app.include_router(public_market_router)
app.include_router(wallet_admin_router)
app.include_router(wallet_router)
app.include_router(bets_router)
app.include_router(settlement_admin_router)
app.include_router(realtime_router)
app.include_router(branding_router)


@app.api_route("/_sentry-test", methods=["GET", "HEAD"])
async def sentry_test() -> dict[str, str]:
    """Synthetic Sentry trigger — D-29. Dev-only; returns 403 in staging/prod."""
    if not settings.is_dev:
        raise HTTPException(status_code=403, detail="not available")
    raise RuntimeError("sentry test from api")
