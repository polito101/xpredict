"""Health and readiness endpoints.

- ``/health``        liveness — no external dependencies, always fast.
- ``/health/ready``  readiness — checks DB connectivity (tolerant; reports per-dep).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.config import settings
from app.db.session import engine

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str
    version: str


class ReadyResponse(BaseModel):
    status: str
    checks: dict[str, str]


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        environment=settings.environment,
        version=settings.version,
    )


@router.get("/health/ready", response_model=ReadyResponse)
async def ready() -> ReadyResponse:
    checks: dict[str, str] = {}

    async def _check_database() -> None:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    try:
        await asyncio.wait_for(_check_database(), timeout=2.0)
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - readiness must never raise
        checks["database"] = f"error: {type(exc).__name__}"

    status = "ok" if all(value == "ok" for value in checks.values()) else "degraded"
    return ReadyResponse(status=status, checks=checks)
