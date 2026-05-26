"""FastAPI app factory — Phase 1 scaffold.

Lifespan:
  - configure_logging(settings) — structlog console/JSON renderer (D-24)
  - init_sentry(service="api", integrations=[FastApiIntegration, SqlalchemyIntegration]) — D-28

Middleware:
  - RequestIdMiddleware (pure ASGI; not BaseHTTPMiddleware per Pattern 6 anti-pattern)
    binds request_id, path, method, client_ip into structlog contextvars (D-26)

Routes:
  - /healthz, /readyz (D-30) via app.routers.health
  - /_sentry-test — synthetic Sentry trigger (D-29); Phase 11 may gate or remove
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import Settings
from app.core.logging import configure_logging
from app.core.sentry import init_sentry
from app.routers import health

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
app.add_middleware(RequestIdMiddleware)
app.include_router(health.router)


@app.api_route("/_sentry-test", methods=["GET", "HEAD"])
async def sentry_test() -> dict[str, str]:
    """Synthetic Sentry trigger — D-29. Phase 11 may gate behind a key."""
    raise RuntimeError("sentry test from api")
