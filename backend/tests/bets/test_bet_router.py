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


def _market(status: str = MARKET_OPEN, *, yes_price: Decimal = Decimal("0.5")) -> MarketView:
    return MarketView(
        id=uuid4(),
        status=status,
        deadline=datetime.now(UTC) + timedelta(days=1),
        outcomes=(
            OutcomeView(id=uuid4(), label="YES", price=yes_price),
            OutcomeView(id=uuid4(), label="NO", price=Decimal("0.5")),
        ),
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
async def test_post_bets_503_when_market_source_unwired(api: httpx.AsyncClient) -> None:
    """With no Phase 4 adapter wired (get_market_source -> None) the endpoint 503s."""
    _auth_as(_User(uuid4()))  # active, not banned; no market source override
    r = await api.post(
        "/bets",
        json={"market_id": str(uuid4()), "outcome_id": str(uuid4()), "stake": "10.0000"},
    )
    assert r.status_code == 503


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
