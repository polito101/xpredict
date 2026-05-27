"""Liveness + readiness endpoints (D-30, PLT-10).

``/healthz`` returns ``{"status": "ok"}`` 200 — no dependency probes. Used by the
backend container's docker-compose healthcheck.

``/readyz`` checks DB (``SELECT 1``) and Redis (``PING``); returns 200 with
``{"status": "ready"}`` when both succeed, 503 with ``{"status": "not_ready",
"failures": {...}}`` otherwise. NEVER leaks connection strings or version info.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.db.session import get_async_session

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe — process is up and the framework is responding."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(
    session: AsyncSession = Depends(get_async_session),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    """Readiness probe — DB + Redis both reachable.

    Returns 200 with ``{"status": "ready"}`` when both deps respond, 503 with
    ``{"status": "not_ready", "failures": {...}}`` otherwise. The ``failures``
    map carries only short error strings — never connection strings.
    """
    failures: dict[str, str] = {}

    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        failures["db"] = type(exc).__name__

    try:
        await redis.ping()
    except Exception as exc:
        failures["redis"] = type(exc).__name__

    if failures:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "failures": failures},
        )
    return {"status": "ready"}
