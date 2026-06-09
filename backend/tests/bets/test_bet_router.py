"""POST /bets — the bet API surface (Phase 5, SC#2: 403 unverified/banned + ACID placement).

Integration tests (testcontainers) through the FastAPI app via httpx ASGITransport. The
market read port is injected via the ``get_market_source`` dependency (``None`` until the
Phase 4 HouseAdapter is wired at integration) — tests override it with a stub. Auth is
exercised by overriding ``current_active_player`` (the Phase 2 cookie gate, active+verified)
with a test user; the NOT-banned check (``current_betting_player``) is XPredict's addition.

The "email_verified_at IS NULL -> 403" half of SC#2 is ``current_active_player``'s behavior
(fastapi-users ``verified=True``), covered by Phase 2 and relied on here; this module covers
the banned -> 403 check, no-auth -> 401, the happy 201 placement, and the domain-error -> HTTP
mapping.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text

from app.auth.deps import current_active_player
from app.bets.market_port import MARKET_CLOSED, MARKET_OPEN, MarketView, OutcomeView
from app.bets.models import Bet
from app.bets.router import get_market_source
from app.db.session import _get_session_maker
from app.main import app
from app.wallet.constants import KIND_USER_WALLET, OWNER_USER, PLAY_USD

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine:
    return engine


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _bets_table(engine: AsyncEngine):
    async with engine.begin() as conn:
        await conn.run_sync(Bet.__table__.create, checkfirst=True)
    yield


@pytest.fixture(autouse=True)
def _clear_overrides():
    """Reset FastAPI dependency overrides after every test — no cross-test leakage."""
    yield
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(loop_scope="session")
async def api() -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --------------------------------------------------------------------------- #
# Stub market source + test user + helpers.
# --------------------------------------------------------------------------- #
class StubMarketSource:
    def __init__(self) -> None:
        self._markets: dict[UUID, MarketView] = {}

    def add(self, m: MarketView) -> MarketView:
        self._markets[m.id] = m
        return m

    async def get_market(self, market_id: UUID) -> MarketView | None:
        return self._markets.get(market_id)


class _User:
    """Minimal stand-in for the authenticated player — only what the endpoint reads."""

    def __init__(self, user_id: UUID, banned_at: datetime | None = None) -> None:
        self.id = user_id
        self.banned_at = banned_at


def _market(
    status: str = MARKET_OPEN,
    *,
    yes_price: Decimal = Decimal("0.5"),
    min_stake: Decimal | None = None,
    max_stake: Decimal | None = None,
) -> MarketView:
    return MarketView(
        id=uuid4(),
        status=status,
        deadline=datetime.now(UTC) + timedelta(days=1),
        outcomes=(
            OutcomeView(id=uuid4(), label="YES", price=yes_price),
            OutcomeView(id=uuid4(), label="NO", price=Decimal("0.5")),
        ),
        min_stake=min_stake,
        max_stake=max_stake,
    )


async def _seed_wallet(balance: Decimal) -> UUID:
    """INSERT a user_wallet at ``balance`` (committed); return its owner user_id."""
    user_id = uuid4()
    sm = _get_session_maker()
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO accounts (id, owner_type, owner_id, kind, currency, balance) "
                "VALUES (:id, :ot, :oid, :k, :c, :b)"
            ),
            {
                "id": uuid4(),
                "ot": OWNER_USER,
                "oid": user_id,
                "k": KIND_USER_WALLET,
                "c": PLAY_USD,
                "b": balance,
            },
        )
    return user_id


async def _seed_bet(user_id: UUID, *, stake: Decimal, odds: Decimal, status: str) -> None:
    """Raw-INSERT a bet in a given status (committed) — for the portfolio read tests."""
    sm = _get_session_maker()
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO bets (id, user_id, market_id, outcome_id, stake, "
                "odds_at_placement, status) VALUES (:id, :u, :m, :o, :st, :od, :status)"
            ),
            {
                "id": uuid4(),
                "u": user_id,
                "m": uuid4(),
                "o": uuid4(),
                "st": stake,
                "od": odds,
                "status": status,
            },
        )


def _auth_as(user: _User) -> None:
    app.dependency_overrides[current_active_player] = lambda: user


def _wire_market(src: StubMarketSource) -> None:
    app.dependency_overrides[get_market_source] = lambda: src


def _payload(m: MarketView, *, stake: str, outcome_idx: int = 0) -> dict:
    return {
        "market_id": str(m.id),
        "outcome_id": str(m.outcomes[outcome_idx].id),
        "stake": stake,
    }


# --------------------------------------------------------------------------- #
# Auth gating (SC#2).
# --------------------------------------------------------------------------- #
async def test_post_bets_requires_auth(api: httpx.AsyncClient) -> None:
    """No cookie -> 401 (the real current_active_player gate, no override)."""
    r = await api.post(
        "/bets",
        json={"market_id": str(uuid4()), "outcome_id": str(uuid4()), "stake": "10.0000"},
    )
    assert r.status_code == 401


async def test_post_bets_403_when_banned(api: httpx.AsyncClient) -> None:
    """A banned player (banned_at set) is 403 — current_betting_player's check."""
    _auth_as(_User(uuid4(), banned_at=datetime.now(UTC)))
    r = await api.post(
        "/bets",
        json={"market_id": str(uuid4()), "outcome_id": str(uuid4()), "stake": "10.0000"},
    )
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
# Wiring + placement.
# --------------------------------------------------------------------------- #
async def test_post_bets_404_when_market_unknown(api: httpx.AsyncClient) -> None:
    """With the REAL market adapter wired (no override), a bet on a non-existent market is
    404 — the market is validated at the app layer via MarketReadPort (integration)."""
    _auth_as(_User(uuid4()))  # active, not banned; the real HouseMarketReadAdapter is wired
    r = await api.post(
        "/bets",
        json={"market_id": str(uuid4()), "outcome_id": str(uuid4()), "stake": "10.0000"},
    )
    assert r.status_code == 404


async def test_post_bets_happy_path_201(api: httpx.AsyncClient) -> None:
    user_id = await _seed_wallet(Decimal("100.0000"))
    _auth_as(_User(user_id))
    src = StubMarketSource()
    m = src.add(_market(yes_price=Decimal("0.4")))
    _wire_market(src)

    r = await api.post("/bets", json=_payload(m, stake="30.0000"))

    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "PENDING"
    assert body["market_id"] == str(m.id)
    assert body["outcome_id"] == str(m.outcomes[0].id)
    # Money + odds are JSON STRINGS, never floats (SC#4 discipline).
    assert isinstance(body["stake"], str)
    assert isinstance(body["odds_at_placement"], str)
    assert Decimal(body["stake"]) == Decimal("30.0000")
    assert Decimal(body["odds_at_placement"]) == Decimal("0.4")


async def test_post_bets_409_when_market_closed(api: httpx.AsyncClient) -> None:
    _auth_as(_User(await _seed_wallet(Decimal("100.0000"))))
    src = StubMarketSource()
    m = src.add(_market(status=MARKET_CLOSED))
    _wire_market(src)
    r = await api.post("/bets", json=_payload(m, stake="10.0000"))
    assert r.status_code == 409


async def test_post_bets_402_when_insufficient_balance(api: httpx.AsyncClient) -> None:
    _auth_as(_User(await _seed_wallet(Decimal("5.0000"))))
    src = StubMarketSource()
    m = src.add(_market())
    _wire_market(src)
    r = await api.post("/bets", json=_payload(m, stake="10.0000"))
    assert r.status_code == 402


async def test_post_bets_422_when_stake_nonpositive(api: httpx.AsyncClient) -> None:
    _auth_as(_User(await _seed_wallet(Decimal("100.0000"))))
    src = StubMarketSource()
    m = src.add(_market())
    _wire_market(src)
    r = await api.post("/bets", json=_payload(m, stake="0"))
    assert r.status_code == 422  # Pydantic Field(gt=0) rejects before the service


# --------------------------------------------------------------------------- #
# Portfolio read (SC#7) — GET /bets/me/portfolio.
# --------------------------------------------------------------------------- #
async def test_get_portfolio_requires_auth(api: httpx.AsyncClient) -> None:
    r = await api.get("/bets/me/portfolio")
    assert r.status_code == 401


async def test_get_portfolio_returns_open_and_settled_with_pnl(api: httpx.AsyncClient) -> None:
    user_id = uuid4()
    await _seed_bet(user_id, stake=Decimal("40.0000"), odds=Decimal("0.5"), status="PENDING")
    await _seed_bet(user_id, stake=Decimal("40.0000"), odds=Decimal("0.5"), status="SETTLED_WON")
    await _seed_bet(user_id, stake=Decimal("60.0000"), odds=Decimal("0.5"), status="SETTLED_LOST")
    _auth_as(_User(user_id))

    r = await api.get("/bets/me/portfolio")

    assert r.status_code == 200
    body = r.json()
    assert len(body["open"]) == 1
    assert len(body["settled"]) == 2
    # Open: potential payout at locked odds, money as a JSON string.
    op = body["open"][0]
    assert isinstance(op["potential_payout"], str)
    assert Decimal(op["potential_payout"]) == Decimal("80.0000")  # 40 / 0.5
    assert Decimal(op["potential_pnl"]) == Decimal("40.0000")
    # Settled: realized P&L (winner positive, loser = -stake).
    won = next(p for p in body["settled"] if p["won"])
    lost = next(p for p in body["settled"] if not p["won"])
    assert Decimal(won["payout"]) == Decimal("80.0000")
    assert Decimal(won["realized_pnl"]) == Decimal("40.0000")
    assert Decimal(lost["payout"]) == Decimal("0.0000")
    assert Decimal(lost["realized_pnl"]) == Decimal("-60.0000")


# --------------------------------------------------------------------------- #
# Stake limits — global fallback + per-market overrides (BET-06, server-side).
#
# The stake check moved from the router into BetService.place_bet (RESEARCH A4) because
# only the service loads the market. A market with NULL min/max_stake therefore falls back
# to the global BET_MIN_STAKE/BET_MAX_STAKE config; a market with explicit limits is checked
# against those. All cases wire a stub market (the check needs the market in hand).
# --------------------------------------------------------------------------- #
async def test_post_bets_422_when_stake_below_global_min(api: httpx.AsyncClient) -> None:
    """A market with NULL limits falls back to the global min — stake below it is 422."""
    _auth_as(_User(await _seed_wallet(Decimal("100.0000"))))
    src = StubMarketSource()
    m = src.add(_market())  # NULL min/max -> global default (1..100000)
    _wire_market(src)
    r = await api.post("/bets", json=_payload(m, stake="0.5"))
    assert r.status_code == 422


async def test_post_bets_422_when_stake_above_global_max(api: httpx.AsyncClient) -> None:
    """A market with NULL limits falls back to the global max — stake above it is 422."""
    _auth_as(_User(await _seed_wallet(Decimal("1000000.0000"))))
    src = StubMarketSource()
    m = src.add(_market())  # NULL min/max -> global default (1..100000)
    _wire_market(src)
    r = await api.post("/bets", json=_payload(m, stake="999999"))
    assert r.status_code == 422


async def test_post_bets_rejects_below_per_market_min(api: httpx.AsyncClient) -> None:
    """A per-market min_stake=10 rejects a stake of 5 at the PER-MARKET limit (422),
    even though 5 is above the global min of 1."""
    _auth_as(_User(await _seed_wallet(Decimal("100.0000"))))
    src = StubMarketSource()
    m = src.add(_market(min_stake=Decimal("10"), max_stake=Decimal("50")))
    _wire_market(src)
    r = await api.post("/bets", json=_payload(m, stake="5"))
    assert r.status_code == 422
    # The 422 detail carries the per-market bounds (not the global ones).
    assert "10" in r.json()["detail"] and "50" in r.json()["detail"]


async def test_post_bets_rejects_above_per_market_max(api: httpx.AsyncClient) -> None:
    """A per-market max_stake=50 rejects a stake of 60 at the PER-MARKET limit (422),
    even though 60 is well below the global max of 100000."""
    _auth_as(_User(await _seed_wallet(Decimal("100.0000"))))
    src = StubMarketSource()
    m = src.add(_market(min_stake=Decimal("10"), max_stake=Decimal("50")))
    _wire_market(src)
    r = await api.post("/bets", json=_payload(m, stake="60"))
    assert r.status_code == 422


async def test_post_bets_accepts_within_per_market_range(api: httpx.AsyncClient) -> None:
    """A stake of 25 inside the per-market [10, 50] range is accepted (201)."""
    user_id = await _seed_wallet(Decimal("100.0000"))
    _auth_as(_User(user_id))
    src = StubMarketSource()
    m = src.add(_market(min_stake=Decimal("10"), max_stake=Decimal("50")))
    _wire_market(src)
    r = await api.post("/bets", json=_payload(m, stake="25.0000"))
    assert r.status_code == 201
    assert Decimal(r.json()["stake"]) == Decimal("25.0000")


async def test_get_portfolio_open_position_uses_live_unrealized_pnl(api: httpx.AsyncClient) -> None:
    """Open P&L is mark-to-market against the LIVE current odds, not the win-scenario payout.

    Bet 40 on YES at 0.5, then YES rises to 0.625 (more likely): current_value =
    40 * 0.625 / 0.5 = 50 -> unrealized_pnl = +10. The win-scenario potential_pnl (+40) is
    separate and unchanged.
    """
    user_id = await _seed_wallet(Decimal("100.0000"))
    _auth_as(_User(user_id))
    market_id = uuid4()
    yes_id = uuid4()
    no_id = uuid4()

    def market_at(yes_price: str) -> MarketView:
        return MarketView(
            id=market_id,
            status=MARKET_OPEN,
            deadline=datetime.now(UTC) + timedelta(days=1),
            outcomes=(
                OutcomeView(id=yes_id, label="YES", price=Decimal(yes_price)),
                OutcomeView(id=no_id, label="NO", price=Decimal("0.5")),
            ),
        )

    src = StubMarketSource()
    src.add(market_at("0.5"))  # entry price
    _wire_market(src)

    r = await api.post(
        "/bets",
        json={"market_id": str(market_id), "outcome_id": str(yes_id), "stake": "40.0000"},
    )
    assert r.status_code == 201

    src.add(market_at("0.625"))  # YES rises -> position gains
    body = (await api.get("/bets/me/portfolio")).json()
    op = next(p for p in body["open"] if p["outcome_id"] == str(yes_id))
    assert op["priced"] is True
    assert Decimal(op["current_value"]) == Decimal("50.0000")
    assert Decimal(op["unrealized_pnl"]) == Decimal("10.0000")
    assert Decimal(op["potential_pnl"]) == Decimal("40.0000")  # 40/0.5 - 40, unchanged


async def test_sell_position_returns_405(api: httpx.AsyncClient) -> None:
    """Selling a position is not supported in v1 — the API returns 405 (SC#3)."""
    _auth_as(_User(uuid4()))
    r = await api.post(f"/bets/{uuid4()}/sell")
    assert r.status_code == 405


async def test_sell_position_requires_auth(api: httpx.AsyncClient) -> None:
    r = await api.post(f"/bets/{uuid4()}/sell")
    assert r.status_code == 401
