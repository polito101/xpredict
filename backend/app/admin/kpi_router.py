"""Admin KPI dashboard router (Phase 10, Plan 10-02, ADD-02/ADD-03).

``GET /api/v1/admin/dashboard/kpis?window=`` — the operator's 5-second health pulse, gated by
``current_active_admin`` (T-10-07: a player Bearer → 403, no Bearer → 401, the same gate Plan
10-01 established for the tenant-config routes). Returns one :class:`KpiResponse` payload with all
five cards + the ≤30-day daily-volume chart buckets.

``window`` is a ``Literal["24h","7d","30d"]`` query param defaulting to ``"24h"`` — an
out-of-allowlist value 422s at FastAPI validation BEFORE the service runs (T-10-09: the interval
is derived from a fixed map, never string-interpolated into SQL). The total query time is logged
at INFO (D-01 observability — makes a "measurably slow" KPI render observable for the
caching-revisit decision).

# The postponed-annotations future import is intentionally ABSENT — FastAPI's
# ``Annotated[T, Depends(...)]`` resolver on Python 3.13 breaks with forward-ref strings (params
# get misread as query params → spurious 422). Same constraint documented in every router file.
"""

import time
from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.kpi_schemas import KpiResponse, VolumeBucket
from app.admin.kpi_service import get_kpis
from app.auth.deps import current_active_admin
from app.auth.models import User
from app.db.session import get_async_session

log = structlog.get_logger()

kpi_router = APIRouter(prefix="/api/v1/admin/dashboard", tags=["admin-dashboard"])


@kpi_router.get("/kpis", response_model=KpiResponse)
async def get_dashboard_kpis(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
    window: Annotated[Literal["24h", "7d", "30d"], Query()] = "24h",
) -> KpiResponse:
    """Return the five KPI cards + the daily volume chart buckets for ``window`` (D-01..D-06).

    ``window`` (24h | 7d | 30d, default 24h) sets the DAU + chart window; any other value 422s
    before this body runs. Read-only — the service issues no writes.
    """
    started = time.perf_counter()
    agg = await get_kpis(session, window=window)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    # D-01 observability: surface the total query time so a future slowdown is measurable.
    log.info("admin.kpi_query", window=window, elapsed_ms=round(elapsed_ms, 2))

    return KpiResponse(
        volume_24h=agg.volume_24h,
        daily_active_users=agg.daily_active_users,
        active_markets=agg.active_markets,
        pending_resolutions=agg.pending_resolutions,
        house_pnl_today=agg.house_pnl_today,
        house_pnl_cumulative=agg.house_pnl_cumulative,
        volume_buckets=[VolumeBucket(day=b.day, volume=b.volume) for b in agg.volume_buckets],
    )


__all__ = ["kpi_router"]
