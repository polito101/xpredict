"""Read-only KPI aggregates for the admin dashboard (Phase 10, Plan 10-02, ADD-02/ADD-03).

One service, all five cards + the 30-day chart buckets, computed server-side over the
EXISTING ledger / bets / markets / audit tables. STRICTLY read-only — no INSERT/UPDATE/commit
(T-10 KPI→tables boundary is read-only). Every money result is a ``Decimal`` the schema
serializes as a string (never a JSON float).

Two formulas are the CORRECTED ones (10-RESEARCH §Flagged Unknowns 1 & 2 — the ROADMAP SC#2
formulas are WRONG against the real schema and MUST NOT be copied verbatim):

  - **House P&L** is NOT ``SUM(house_revenue) − SUM(house-expense-account)`` — no such
    house-expense account exists. It is the kind-filtered net flow:
    ``Σ(settle_loss credit→house_revenue) − Σ(settle_winnings debit→house_promo)``, with the
    ``reverse_*`` legs netted so a reversed settlement leaves no phantom P&L. The transfer
    kinds + house account UUIDs are IMPORTED (``TRANSFER_SETTLE_*`` / ``TRANSFER_REVERSE_*`` /
    ``HOUSE_*_ACCOUNT_ID``) — never hardcoded. The account-constrained arm hits
    ``entries_account_idx``.
  - **DAU** is NOT logins-only — bets emit no audit event, so an audit-only DAU undercounts
    bettors. It is the distinct UNION of bettors (``bets.created_at``) and player logins
    (``audit_log`` filtered on the REAL emitted event ``auth.session_started`` — NOT the stale
    ``auth.login_*``), with admin logins (``auth.admin_login_started``) excluded.

"Today" boundary uses UTC ``date_trunc('day', now())`` for the lower bound and ``now()`` for the
upper bound — the documented project default (A1: all ``created_at`` / ``occurred_at`` columns
are ``DateTime(timezone=True)``; there is no per-tenant display timezone).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import case, cast, func, select
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.bets.models import Bet
from app.core.audit.models import AuditLog
from app.markets.enums import MarketStatus
from app.markets.models import Market
from app.settlement.constants import (
    TRANSFER_REVERSE_LOSS,
    TRANSFER_REVERSE_WINNINGS,
    TRANSFER_SETTLE_LOSS,
    TRANSFER_SETTLE_WINNINGS,
)
from app.wallet.constants import (
    DIRECTION_CREDIT,
    DIRECTION_DEBIT,
    HOUSE_PROMO_ACCOUNT_ID,
    HOUSE_REVENUE_ACCOUNT_ID,
)
from app.wallet.models import Entry, Transfer

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# The login event the auth router actually emits on a successful PLAYER login
# (app/auth/router.py). The stale ``auth.login_*`` literal in KNOWN_EVENT_TYPES is
# never emitted, so it must NOT be used here. Admin logins emit
# ``auth.admin_login_started``, which this filter deliberately excludes (DAU = players, A2).
AUTH_SESSION_STARTED = "auth.session_started"

# The four settlement/reversal transfer kinds that move money across a house account.
_PNL_KINDS = (
    TRANSFER_SETTLE_LOSS,
    TRANSFER_REVERSE_LOSS,
    TRANSFER_SETTLE_WINNINGS,
    TRANSFER_REVERSE_WINNINGS,
)


@dataclass(frozen=True, slots=True)
class VolumeBucketRow:
    """One ``(day, volume)`` row of the daily-volume chart."""

    day: datetime
    volume: Decimal


@dataclass(frozen=True, slots=True)
class KpiAggregates:
    """The computed KPI values (money as ``Decimal``; the schema stringifies them)."""

    volume_24h: Decimal
    daily_active_users: int
    active_markets: int
    pending_resolutions: int
    house_pnl_today: Decimal
    house_pnl_cumulative: Decimal
    volume_buckets: list[VolumeBucketRow]


_WINDOW_HOURS: dict[str, int] = {"24h": 24, "7d": 168, "30d": 720}


def window_to_hours(window: str) -> int:
    """Translate the validated window param to its hour count (24 / 168 / 720)."""
    return _WINDOW_HOURS[window]


async def house_pnl(
    session: AsyncSession, *, lo: datetime | None = None, hi: datetime | None = None
) -> Decimal:
    """House P&L over ``[lo, hi)`` — net ``settle_loss − settle_winnings`` (reverse_* netted).

    Strategy B (kind-filtered net flow, 10-RESEARCH §Flagged Unknown 1): robust to
    ``house_promo`` also funding recharges / signup bonuses (those are NOT house P&L) because
    we filter on the settlement transfer KINDS, not raw balances. The revenue arm is constrained
    to the ``house_revenue`` credit leg and the expense arm to the ``house_promo`` debit leg so
    each ``CASE`` hits ``entries_account_idx``. Omit ``lo`` for the cumulative figure.
    """
    revenue_case = func.coalesce(
        func.sum(
            case(
                (
                    (Transfer.kind == TRANSFER_SETTLE_LOSS)
                    & (Entry.account_id == HOUSE_REVENUE_ACCOUNT_ID)
                    & (Entry.direction == DIRECTION_CREDIT),
                    Entry.amount,
                ),
                (
                    (Transfer.kind == TRANSFER_REVERSE_LOSS)
                    & (Entry.account_id == HOUSE_REVENUE_ACCOUNT_ID)
                    & (Entry.direction == DIRECTION_DEBIT),
                    -Entry.amount,
                ),
                else_=0,
            )
        ),
        0,
    )
    expense_case = func.coalesce(
        func.sum(
            case(
                (
                    (Transfer.kind == TRANSFER_SETTLE_WINNINGS)
                    & (Entry.account_id == HOUSE_PROMO_ACCOUNT_ID)
                    & (Entry.direction == DIRECTION_DEBIT),
                    Entry.amount,
                ),
                (
                    (Transfer.kind == TRANSFER_REVERSE_WINNINGS)
                    & (Entry.account_id == HOUSE_PROMO_ACCOUNT_ID)
                    & (Entry.direction == DIRECTION_CREDIT),
                    -Entry.amount,
                ),
                else_=0,
            )
        ),
        0,
    )

    stmt = (
        select((revenue_case - expense_case).label("pnl"))
        .select_from(Entry)
        .join(Transfer, Entry.transfer_id == Transfer.id)
        .where(Transfer.kind.in_(_PNL_KINDS))
    )
    if lo is not None:
        stmt = stmt.where(Entry.created_at >= lo)
    if hi is not None:
        stmt = stmt.where(Entry.created_at < hi)

    result = (await session.execute(stmt)).scalar_one()
    return Decimal(result)


async def dau(session: AsyncSession, *, window_hours: int) -> int:
    """Distinct active users = UNION(bettors, player logins) over the window (A2: no admins).

    Bettors: ``select(Bet.user_id) WHERE created_at >= lo``. Logins: the user id parsed from
    ``audit_log.actor`` (``user:<uuid>``) for ``auth.session_started`` rows in the window.
    ``UNION`` (set, not ``UNION ALL``) dedups a user who both bet and logged in.
    """
    lo = datetime.now(UTC) - timedelta(hours=window_hours)

    bettors = select(Bet.user_id.label("uid")).where(Bet.created_at >= lo)
    logins = select(
        cast(func.split_part(AuditLog.actor, ":", 2), PG_UUID(as_uuid=True)).label("uid")
    ).where(
        AuditLog.event_type == AUTH_SESSION_STARTED,
        AuditLog.occurred_at >= lo,
        # Exact 'user:' + 36-char UUID form (WR-02). `LIKE 'user:%'` also matches a
        # bare 'user:' (the % matches empty), and `split_part('user:', ':', 2)`
        # yields '' → CAST('' AS uuid) raises and 500s the WHOLE KPI endpoint.
        # `audit_log` is append-only, so one degenerate actor row could not be
        # purged — gate the cast on a strict regex instead of an open prefix.
        AuditLog.actor.op("~")(r"^user:[0-9a-fA-F-]{36}$"),
    )
    active = bettors.union(logins).subquery()
    return int((await session.execute(select(func.count()).select_from(active))).scalar_one())


async def active_markets(session: AsyncSession) -> int:
    """COUNT of markets currently OPEN for betting (D-02)."""
    stmt = select(func.count()).select_from(Market).where(Market.status == MarketStatus.OPEN.value)
    return int((await session.execute(stmt)).scalar_one())


async def pending_resolutions(session: AsyncSession) -> int:
    """COUNT of markets past their deadline and not yet finalized (D-04, A3 excludes DRAFT).

    ``deadline < now() AND status NOT IN (RESOLVED, CANCELLED, DRAFT)`` — a single ``deadline``
    column for both HOUSE and POLYMARKET sources (no separate end-date column exists). A
    never-opened DRAFT past a placeholder deadline is NOT "pending resolution".
    """
    excluded = (
        MarketStatus.RESOLVED.value,
        MarketStatus.CANCELLED.value,
        MarketStatus.DRAFT.value,
    )
    stmt = (
        select(func.count())
        .select_from(Market)
        .where(Market.deadline < func.now(), Market.status.notin_(excluded))
    )
    return int((await session.execute(stmt)).scalar_one())


async def volume_24h(session: AsyncSession) -> Decimal:
    """SUM(bets.stake) over the last 24h (D-02); COALESCE 0 when there are no bets.

    Uses ``bets.stake`` — NOT ``markets.volume`` / ``volume_24hr`` (those are Polymarket
    replication fields, external data, not internal stake totals).
    """
    lo = datetime.now(UTC) - timedelta(hours=24)
    stmt = select(func.coalesce(func.sum(Bet.stake), 0)).where(Bet.created_at >= lo)
    return Decimal((await session.execute(stmt)).scalar_one())


async def daily_volume_buckets(
    session: AsyncSession, *, window_hours: int
) -> list[VolumeBucketRow]:
    """Daily ``(date_trunc('day', created_at), SUM(stake))`` buckets over the window (D-06).

    ≤30 daily points for the 30-day chart — server-side bucketing (no client downsampling).
    """
    lo = datetime.now(UTC) - timedelta(hours=window_hours)
    day = func.date_trunc("day", Bet.created_at).label("day")
    stmt = (
        select(day, func.coalesce(func.sum(Bet.stake), 0).label("volume"))
        .where(Bet.created_at >= lo)
        .group_by(day)
        .order_by(day)
    )
    rows = (await session.execute(stmt)).all()
    return [VolumeBucketRow(day=row.day, volume=Decimal(row.volume)) for row in rows]


async def get_kpis(session: AsyncSession, *, window: str) -> KpiAggregates:
    """Compute all five cards + the daily volume buckets for ``window`` (24h | 7d | 30d).

    "Today" for the house-P&L-today card is the UTC calendar day: ``lo`` is
    ``date_trunc('day', now())`` and ``hi`` is ``now()`` (A1 — the documented project default;
    all timestamps are tz-aware UTC, there is no per-tenant display timezone). The DAU + chart
    windows follow ``window``; volume_24h / active / pending are fixed-window or point-in-time.
    """
    window_hours = window_to_hours(window)
    now = datetime.now(UTC)
    today_lo = now.replace(hour=0, minute=0, second=0, microsecond=0)

    return KpiAggregates(
        volume_24h=await volume_24h(session),
        daily_active_users=await dau(session, window_hours=window_hours),
        active_markets=await active_markets(session),
        pending_resolutions=await pending_resolutions(session),
        house_pnl_today=await house_pnl(session, lo=today_lo, hi=now),
        house_pnl_cumulative=await house_pnl(session),
        volume_buckets=await daily_volume_buckets(session, window_hours=window_hours),
    )
