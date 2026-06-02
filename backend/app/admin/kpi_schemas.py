"""Admin KPI dashboard response schemas (Phase 10, Plan 10-02, ADD-02/ADD-03).

The one payload the operator's 5-second health pulse renders: the five cards
(24h volume, DAU, active markets, pending resolutions, house P&L today +
cumulative) plus the ≤30-day daily-volume chart buckets.

Money discipline (SC#4 / WAL-05): every Decimal field is typed ``MoneyStr`` — the
money-as-JSON-string contract reused VERBATIM from ``app/admin/schemas.py`` (which
imports it from ``app/wallet/schemas.py``). ``house_pnl_*`` may be NEGATIVE (the
house funded more winnings than it swept in losses); a negative P&L serializes as
a negative string, never a JSON float. The ``scripts/lint_money_columns.py`` CI
gate enforces the contract.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.wallet.schemas import MoneyStr


class VolumeBucket(BaseModel):
    """One daily bucket of the 30-day volume chart (ADD-03).

    ``day`` is the UTC ``date_trunc('day', bets.created_at)`` boundary; ``volume``
    is the summed stake for that day as a money STRING. The frontend (Plan 10-04)
    renders ``<1`` bucket as the friendly empty state.
    """

    day: datetime
    volume: MoneyStr


class KpiResponse(BaseModel):
    """The admin dashboard KPI payload — five cards + the 30-day chart buckets.

    ``daily_active_users`` is a COUNT (no per-user ids ever cross the boundary —
    T-10-08). ``house_pnl_today`` / ``house_pnl_cumulative`` may be negative.
    ``volume_buckets`` carries ≤30 daily points for the volume-over-time chart.
    """

    volume_24h: MoneyStr
    daily_active_users: int
    active_markets: int
    pending_resolutions: int
    house_pnl_today: MoneyStr
    house_pnl_cumulative: MoneyStr
    volume_buckets: list[VolumeBucket]
