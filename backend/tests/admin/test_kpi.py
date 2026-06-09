"""Admin KPI dashboard endpoint — integration tests (Phase 10, Plan 10-02, ADD-02/ADD-03).

Read-only aggregates over the EXISTING ledger / bets / markets / audit tables, served by
``GET /api/v1/admin/dashboard/kpis?window=`` (admin-Bearer-gated). The two highest-value
sentinels guard the two CORRECTED formulas (10-RESEARCH §Flagged Unknowns 1 & 2):

  - **House P&L** is the kind-filtered net flow ``settle_loss - settle_winnings`` (NOT a
    non-existent ``house_expense`` account), with ``reverse_*`` netted — a reversal returns
    P&L to its pre-settlement value. Driven through a REAL ``SettlementService.resolve_market``
    so the assertion is against actual ledger entries, never hand-posted rows.
  - **DAU** is the distinct UNION of bettors (``bets.created_at``) and player logins
    (``audit_log`` ``auth.session_started``); admin logins (``auth.admin_login_started``) are
    excluded and a user who both bet and logged in is counted once.

The container is session-scoped (committed writes persist across tests), so house-P&L
assertions use before/after DELTAS and DAU/markets assertions scope to a fresh per-test
window / fresh UUIDs. ``audit_log`` is append-only (WAL-06) — login rows can never be
cleaned up, so the DAU window is kept tight (a few minutes) and keyed on fresh user UUIDs.

# ``from __future__ import annotations`` is intentionally ABSENT (mirrors the settlement
# tests) — irrelevant here but consistent with the project test style.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from app.bets.market_port import MARKET_OPEN, MarketView, OutcomeView
from app.bets.service import BetService
from app.db.session import _get_session_maker
from app.settlement.service import SettlementService
from app.wallet.constants import KIND_USER_WALLET, OWNER_USER, PLAY_USD
from app.wallet.service import WalletService
from tests.admin._helpers import (
    auth,
    client,
    get_admin_token,
    seed_audit,
    seed_bet,
    seed_market,
    seed_user,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]

KPIS_URL = "/api/v1/admin/dashboard/kpis"


@pytest.fixture(autouse=True)
def _require_testcontainer(engine: "AsyncEngine") -> "AsyncEngine":
    """Depend on ``engine`` (container, migrate, env rewrite) — mirrors the settlement tests."""
    return engine


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _admin_user(engine: "AsyncEngine"):
    """Ensure the shared admin account exists so ``get_admin_token`` can mint a Bearer."""
    from tests.admin._helpers import ADMIN_EMAIL

    await seed_user(engine, ADMIN_EMAIL, is_superuser=True, display_name="KPI Admin")
    yield


# --------------------------------------------------------------------------- #
# House-P&L seam — a REAL settlement (StubMarketSource + BetService + Settlement).
# Mirrors tests/settlement/test_resolve_market.py exactly.
# --------------------------------------------------------------------------- #
class _StubMarketSource:
    def __init__(self) -> None:
        self._markets: dict[UUID, MarketView] = {}

    def add(self, market: MarketView) -> MarketView:
        self._markets[market.id] = market
        return market

    async def get_market(self, market_id: UUID) -> MarketView | None:
        return self._markets.get(market_id)


class _FakeMarketResolver:
    """In-memory ``MarketResolvePort`` — records resolutions + reopenings."""

    def __init__(self) -> None:
        self.resolved: list[tuple[UUID, UUID]] = []
        self.reopened: list[UUID] = []

    async def mark_resolved(
        self,
        session,
        *,
        market_id: UUID,
        winning_outcome_id: UUID,
        resolution_source: str,
        justification: str,
    ) -> None:
        self.resolved.append((market_id, winning_outcome_id))

    async def mark_unresolved(self, session, *, market_id: UUID) -> None:
        self.reopened.append(market_id)


def _binary_market() -> MarketView:
    return MarketView(
        id=uuid4(),
        status=MARKET_OPEN,
        deadline=datetime.now(UTC) + timedelta(days=1),
        outcomes=(
            OutcomeView(id=uuid4(), label="YES", price=Decimal("0.5")),
            OutcomeView(id=uuid4(), label="NO", price=Decimal("0.5")),
        ),
    )


async def _seed_wallet(balance: Decimal) -> tuple[UUID, UUID]:
    """Create a LEDGER-BACKED user_wallet at ``balance`` (committed); return (user_id, wallet_id).

    INSERTs at balance 0, then funds via the real ``WalletService.recharge``. ``house_pnl`` is
    kind-filtered (``settle_*`` / ``reverse_*``) so the ``recharge`` funding is excluded from the
    P&L deltas this suite asserts; ledger-backing keeps the committed wallet from leaking drift
    into other suites' DB-wide ledger-integrity gate (e.g. ``tests/settlement/test_event_*``).
    """
    from sqlalchemy import text

    user_id = uuid4()
    wallet_id = uuid4()
    sm = _get_session_maker()
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO accounts (id, owner_type, owner_id, kind, currency, balance) "
                "VALUES (:id, :ot, :oid, :kind, :cur, :bal)"
            ),
            {
                "id": wallet_id,
                "ot": OWNER_USER,
                "oid": user_id,
                "kind": KIND_USER_WALLET,
                "cur": PLAY_USD,
                "bal": Decimal("0"),
            },
        )
    if balance > 0:
        async with sm() as s:
            await WalletService.recharge(
                s,
                user_id=user_id,
                amount=balance,
                reason="test seed",
                idempotency_key=f"seed:{wallet_id}",
            )
    return user_id, wallet_id


async def _place(user_id: UUID, market: MarketView, outcome_id: UUID, stake: Decimal, src) -> None:
    sm = _get_session_maker()
    async with sm() as s:
        await BetService.place_bet(
            s,
            user_id=user_id,
            market_id=market.id,
            outcome_id=outcome_id,
            stake=stake,
            market_source=src,
        )


async def _resolve(market: MarketView, winning_outcome_id: UUID, resolver) -> None:
    sm = _get_session_maker()
    async with sm() as s:
        await SettlementService.resolve_market(
            s,
            market_id=market.id,
            winning_outcome_id=winning_outcome_id,
            market_resolver=resolver,
            justification="resolved for the KPI P&L seam",
        )


async def _fetch_kpis(window: str = "24h") -> tuple[int, dict]:
    """GET the admin KPI endpoint as the seeded admin; return (status_code, json)."""
    c = await client()
    async with c:
        token = await get_admin_token(c)
        resp = await c.get(KPIS_URL, params={"window": window}, headers=auth(token))
    return resp.status_code, (resp.json() if resp.content else {})


async def _raw_kpis(window: str = "24h") -> tuple[int, str]:
    """GET the KPI endpoint; return (status_code, raw JSON text) for money-as-string asserts."""
    c = await client()
    async with c:
        token = await get_admin_token(c)
        resp = await c.get(KPIS_URL, params={"window": window}, headers=auth(token))
    return resp.status_code, resp.text


# --------------------------------------------------------------------------- #
# House P&L (the highest-value sentinel) — net settle_loss - settle_winnings,
# reversal nets to zero, more-losers → positive, all-winners → negative.
# --------------------------------------------------------------------------- #
async def test_house_pnl(engine: "AsyncEngine") -> None:
    # Baseline cumulative P&L (the container carries prior tests' settlements).
    status0, body0 = await _fetch_kpis("24h")
    assert status0 == 200, f"KPI endpoint not GREEN yet: {status0}"
    pnl_before = Decimal(body0["house_pnl_cumulative"])

    # A more-losers market → positive house P&L:
    #   2 losers stake 60 each → +120 to house_revenue (settle_loss)
    #   1 winner stakes 40 @ 0.5 → winnings 40 paid from house_promo (settle_winnings)
    #   net = 120 - 40 = +80.
    src = _StubMarketSource()
    m = src.add(_binary_market())
    yes, no = m.outcomes
    winner, _ = await _seed_wallet(Decimal("200.0000"))
    loser1, _ = await _seed_wallet(Decimal("200.0000"))
    loser2, _ = await _seed_wallet(Decimal("200.0000"))
    await _place(winner, m, yes.id, Decimal("40.0000"), src)
    await _place(loser1, m, no.id, Decimal("60.0000"), src)
    await _place(loser2, m, no.id, Decimal("60.0000"), src)

    resolver = _FakeMarketResolver()
    await _resolve(m, yes.id, resolver)

    _, body1 = await _fetch_kpis("24h")
    pnl_after = Decimal(body1["house_pnl_cumulative"])
    assert pnl_after - pnl_before == Decimal("80.0000")

    # Reverse the settlement → P&L must return to the pre-settlement value (reverse_* nets).
    sm = _get_session_maker()
    async with sm() as s:
        await SettlementService.reverse_settlement(
            s,
            market_id=m.id,
            market_resolver=resolver,
            justification="reverse the KPI P&L seam",
        )
    _, body2 = await _fetch_kpis("24h")
    assert Decimal(body2["house_pnl_cumulative"]) == pnl_before

    # An all-winners market yields NEGATIVE P&L (house funds winnings, earns no loss sweep).
    src2 = _StubMarketSource()
    m2 = src2.add(_binary_market())
    yes2, _no2 = m2.outcomes
    w, _ = await _seed_wallet(Decimal("200.0000"))
    await _place(w, m2, yes2.id, Decimal("30.0000"), src2)  # @0.5 → winnings 30 from promo
    await _resolve(m2, yes2.id, _FakeMarketResolver())
    _, body3 = await _fetch_kpis("24h")
    assert Decimal(body3["house_pnl_cumulative"]) - pnl_before == Decimal("-30.0000")


# --------------------------------------------------------------------------- #
# DAU — distinct UNION of bettors + auth.session_started logins; admins excluded.
# --------------------------------------------------------------------------- #
async def test_dau(engine: "AsyncEngine") -> None:
    now = datetime.now(UTC)
    bettor = await seed_user(engine, "kpi-dau-bettor@test.com", display_name="Bettor")
    logger_in = await seed_user(engine, "kpi-dau-login@test.com", display_name="LoginOnly")
    both = await seed_user(engine, "kpi-dau-both@test.com", display_name="Both")

    # (a) a user who ONLY bet; (b) a user who ONLY logged in; (c) a user who did BOTH.
    await seed_bet(engine, bettor, stake=Decimal("5.0000"), created_at=now)
    await seed_audit(event_type="auth.session_started", actor=f"user:{logger_in}")
    await seed_bet(engine, both, stake=Decimal("5.0000"), created_at=now)
    await seed_audit(event_type="auth.session_started", actor=f"user:{both}")

    # An admin login MUST NOT be counted (DAU = players, A2).
    admin_user = await seed_user(engine, "kpi-dau-admin@test.com", is_superuser=True)
    await seed_audit(event_type="auth.admin_login_started", actor=f"user:{admin_user}")

    status, body = await _fetch_kpis("24h")
    assert status == 200
    # At least the 3 distinct users seeded here are active in the 24h window; the
    # admin login does not add a 4th for THESE users (the UNION dedups `both`).
    dau_24h = body["daily_active_users"]
    assert dau_24h >= 3

    # Spread activity across days: a 30d-only bettor shows up in 30d, not 24h.
    old_bettor = await seed_user(engine, "kpi-dau-old@test.com", display_name="OldBettor")
    await seed_bet(engine, old_bettor, stake=Decimal("5.0000"), created_at=now - timedelta(days=10))
    _, body_24 = await _fetch_kpis("24h")
    _, body_30 = await _fetch_kpis("30d")
    # The 10-day-old bettor is in the 30d window but NOT the 24h window.
    assert body_30["daily_active_users"] > body_24["daily_active_users"]


# --------------------------------------------------------------------------- #
# Pending resolutions — deadline < now AND status NOT IN (RESOLVED, CANCELLED, DRAFT).
# --------------------------------------------------------------------------- #
async def test_pending_resolutions(engine: "AsyncEngine") -> None:
    now = datetime.now(UTC)
    past = now - timedelta(hours=1)
    future = now + timedelta(days=2)

    status0, body0 = await _fetch_kpis("24h")
    assert status0 == 200
    pending_before = body0["pending_resolutions"]

    # COUNTED: past deadline + OPEN / CLOSED (not finalized).
    await seed_market(engine, status="OPEN", deadline=past)
    await seed_market(engine, status="CLOSED", deadline=past)
    # NOT counted: past deadline but already finalized.
    await seed_market(engine, status="RESOLVED", deadline=past)
    await seed_market(engine, status="CANCELLED", deadline=past)
    # NOT counted: past deadline but DRAFT (never opened — A3 exclusion).
    await seed_market(engine, status="DRAFT", deadline=past)
    # NOT counted: future deadline (not yet pending), even if OPEN.
    await seed_market(engine, status="OPEN", deadline=future)

    _, body1 = await _fetch_kpis("24h")
    assert body1["pending_resolutions"] - pending_before == 2


# --------------------------------------------------------------------------- #
# Active markets — COUNT(status == OPEN).
# --------------------------------------------------------------------------- #
async def test_active_markets(engine: "AsyncEngine") -> None:
    now = datetime.now(UTC)
    status0, body0 = await _fetch_kpis("24h")
    assert status0 == 200
    active_before = body0["active_markets"]

    await seed_market(engine, status="OPEN", deadline=now + timedelta(days=1))
    await seed_market(engine, status="OPEN", deadline=now + timedelta(days=1))
    await seed_market(engine, status="CLOSED", deadline=now + timedelta(days=1))
    await seed_market(engine, status="DRAFT", deadline=now + timedelta(days=1))

    _, body1 = await _fetch_kpis("24h")
    assert body1["active_markets"] - active_before == 2


# --------------------------------------------------------------------------- #
# 24h volume — SUM(bets.stake) within the last 24h; COALESCE 0 when none.
# --------------------------------------------------------------------------- #
async def test_volume_24h(engine: "AsyncEngine") -> None:
    now = datetime.now(UTC)
    status0, body0 = await _fetch_kpis("24h")
    assert status0 == 200
    vol_before = Decimal(body0["volume_24h"])

    vol_user = await seed_user(engine, "kpi-vol@test.com", display_name="Volumer")
    await seed_bet(engine, vol_user, stake=Decimal("12.5000"), created_at=now)
    await seed_bet(engine, vol_user, stake=Decimal("7.5000"), created_at=now)
    # A bet OUTSIDE the 24h window must NOT add to the 24h volume.
    await seed_bet(engine, vol_user, stake=Decimal("99.0000"), created_at=now - timedelta(days=2))

    _, body1 = await _fetch_kpis("24h")
    assert Decimal(body1["volume_24h"]) - vol_before == Decimal("20.0000")


# --------------------------------------------------------------------------- #
# 30-day chart buckets — ≤30 daily points (date_trunc day).
# --------------------------------------------------------------------------- #
async def test_volume_buckets(engine: "AsyncEngine") -> None:
    from tests.admin._helpers import seed_bet_span

    chart_user = await seed_user(engine, "kpi-chart@test.com", display_name="Chartist")
    await seed_bet_span(engine, chart_user, stake=Decimal("3.0000"), days=30, per_day=1)

    status, body = await _fetch_kpis("30d")
    assert status == 200
    buckets = body["volume_buckets"]
    assert isinstance(buckets, list)
    assert 0 < len(buckets) <= 30
    # Each bucket carries a day + a money STRING volume.
    for b in buckets:
        assert isinstance(b["volume"], str)
        assert "day" in b


# --------------------------------------------------------------------------- #
# Money-as-string on the wire — every money field is a JSON string, never a float.
# A negative P&L renders as a negative string.
# --------------------------------------------------------------------------- #
async def test_money_fields_serialize_as_strings(engine: "AsyncEngine") -> None:
    import json

    status, raw = await _raw_kpis("24h")
    assert status == 200
    parsed = json.loads(raw)
    for field in ("volume_24h", "house_pnl_today", "house_pnl_cumulative"):
        assert isinstance(
            parsed[field], str
        ), f"{field} must be a JSON string, got {parsed[field]!r}"
    # The raw JSON text must quote the money values (no bare float tokens).
    assert f'"volume_24h": "{parsed["volume_24h"]}"' in raw or '"volume_24h":"' in raw


# --------------------------------------------------------------------------- #
# window query param — out-of-allowlist value → 422 BEFORE the service runs.
# --------------------------------------------------------------------------- #
async def test_window_param_rejects_bogus(engine: "AsyncEngine") -> None:
    c = await client()
    async with c:
        token = await get_admin_token(c)
        resp = await c.get(KPIS_URL, params={"window": "bogus"}, headers=auth(token))
    assert resp.status_code == 422


async def test_window_param_defaults_to_24h(engine: "AsyncEngine") -> None:
    c = await client()
    async with c:
        token = await get_admin_token(c)
        resp = await c.get(KPIS_URL, headers=auth(token))  # no window param
    assert resp.status_code == 200
