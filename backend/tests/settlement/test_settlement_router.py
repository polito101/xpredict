"""Admin settlement surface (Phase 5, SC#5 + SC#8) — resolve & reverse endpoints.

Integration tests (testcontainers) through the FastAPI app via httpx ASGITransport.
``current_active_admin`` (the Phase 2 admin Bearer gate) is overridden with a fake admin;
the ``MarketResolvePort`` is injected via ``get_market_resolver`` (None until Phase 4 is
wired at integration -> 503; tests override it with a fake). Bets are placed first via
``BetService.place_bet`` (committed), then the admin endpoint resolves/reverses them.
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
from sqlalchemy import select, text

from app.auth.deps import current_active_admin
from app.bets.market_port import MARKET_OPEN, MarketView, OutcomeView
from app.bets.models import Bet
from app.bets.service import BetService
from app.db.session import _get_session_maker
from app.main import app
from app.settlement.router import get_market_resolver
from app.wallet.constants import KIND_USER_WALLET, OWNER_USER, PLAY_USD
from app.wallet.models import Account

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
    yield
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(loop_scope="session")
async def api() -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class StubMarketSource:
    def __init__(self) -> None:
        self._markets: dict[UUID, MarketView] = {}

    def add(self, m: MarketView) -> MarketView:
        self._markets[m.id] = m
        return m

    async def get_market(self, market_id: UUID) -> MarketView | None:
        return self._markets.get(market_id)


class FakeMarketResolver:
    def __init__(self) -> None:
        self.resolved: list[tuple[UUID, UUID]] = []
        self.reopened: list[UUID] = []

    async def mark_resolved(self, session, *, market_id: UUID, winning_outcome_id: UUID) -> None:
        self.resolved.append((market_id, winning_outcome_id))

    async def mark_unresolved(self, session, *, market_id: UUID) -> None:
        self.reopened.append(market_id)


class _Admin:
    def __init__(self, user_id: UUID) -> None:
        self.id = user_id


def _market() -> MarketView:
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
    user_id, wallet_id = uuid4(), uuid4()
    sm = _get_session_maker()
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO accounts (id, owner_type, owner_id, kind, currency, balance) "
                "VALUES (:id, :ot, :oid, :k, :c, :b)"
            ),
            {
                "id": wallet_id,
                "ot": OWNER_USER,
                "oid": user_id,
                "k": KIND_USER_WALLET,
                "c": PLAY_USD,
                "b": balance,
            },
        )
    return user_id, wallet_id


async def _balance(account_id: UUID) -> Decimal:
    sm = _get_session_maker()
    async with sm() as s:
        return (
            await s.execute(select(Account.balance).where(Account.id == account_id))
        ).scalar_one()


async def _place(user_id: UUID, m: MarketView, outcome_id: UUID, stake: Decimal, src) -> None:
    sm = _get_session_maker()
    async with sm() as s:
        await BetService.place_bet(
            s,
            user_id=user_id,
            market_id=m.id,
            outcome_id=outcome_id,
            stake=stake,
            market_source=src,
        )


def _admin(user_id: UUID) -> None:
    app.dependency_overrides[current_active_admin] = lambda: _Admin(user_id)


def _resolver(r: FakeMarketResolver) -> None:
    app.dependency_overrides[get_market_resolver] = lambda: r


# --------------------------------------------------------------------------- #
# Resolve endpoint (SC#5).
# --------------------------------------------------------------------------- #
async def test_resolve_requires_admin(api: httpx.AsyncClient) -> None:
    """No admin Bearer -> 401 (the real current_active_admin gate, no override)."""
    r = await api.post(
        f"/admin/markets/{uuid4()}/resolve",
        json={"winning_outcome_id": str(uuid4()), "justification": "x"},
    )
    assert r.status_code == 401


async def test_resolve_503_when_resolver_unwired(api: httpx.AsyncClient) -> None:
    _admin(uuid4())  # no resolver override -> get_market_resolver returns None
    r = await api.post(
        f"/admin/markets/{uuid4()}/resolve",
        json={"winning_outcome_id": str(uuid4()), "justification": "x"},
    )
    assert r.status_code == 503


async def test_resolve_422_when_justification_blank(api: httpx.AsyncClient) -> None:
    _admin(uuid4())
    _resolver(FakeMarketResolver())
    r = await api.post(
        f"/admin/markets/{uuid4()}/resolve",
        json={"winning_outcome_id": str(uuid4()), "justification": ""},
    )
    assert r.status_code == 422  # Field(min_length=1) — justification is mandatory (SC#5)


async def test_resolve_happy_path_settles_and_returns_summary(api: httpx.AsyncClient) -> None:
    src = StubMarketSource()
    m = src.add(_market())
    yes, no = m.outcomes
    alice, alice_w = await _seed_wallet(Decimal("100.0000"))
    bob, _bob_w = await _seed_wallet(Decimal("100.0000"))
    await _place(alice, m, yes.id, Decimal("40.0000"), src)  # winner
    await _place(bob, m, no.id, Decimal("60.0000"), src)  # loser

    resolver = FakeMarketResolver()
    _admin(uuid4())
    _resolver(resolver)

    r = await api.post(
        f"/admin/markets/{m.id}/resolve",
        json={"winning_outcome_id": str(yes.id), "justification": "YES per official source"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["market_id"] == str(m.id)
    assert body["winning_outcome_id"] == str(yes.id)
    assert body["bets_settled"] == 2
    assert Decimal(body["total_payout"]) == Decimal("80.0000")
    assert Decimal(body["total_loser_stake"]) == Decimal("60.0000")
    assert isinstance(body["total_payout"], str)  # money-as-string (SC#4)
    # The settlement actually ran: Alice paid 40 / 0.5 = 80 -> 60 + 80 = 140.
    assert await _balance(alice_w) == Decimal("140.0000")
    assert resolver.resolved == [(m.id, yes.id)]


# --------------------------------------------------------------------------- #
# Reverse endpoint (SC#8).
# --------------------------------------------------------------------------- #
async def test_reverse_happy_path_restores_and_returns_count(api: httpx.AsyncClient) -> None:
    src = StubMarketSource()
    m = src.add(_market())
    yes, no = m.outcomes
    alice, alice_w = await _seed_wallet(Decimal("100.0000"))
    await _place(alice, m, yes.id, Decimal("40.0000"), src)

    resolver = FakeMarketResolver()
    _admin(uuid4())
    _resolver(resolver)

    # Resolve, then reverse — both via the admin API.
    await api.post(
        f"/admin/markets/{m.id}/resolve",
        json={"winning_outcome_id": str(yes.id), "justification": "settle"},
    )
    assert await _balance(alice_w) == Decimal("140.0000")

    r = await api.post(
        f"/admin/markets/{m.id}/reverse",
        json={"justification": "wrong source"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["market_id"] == str(m.id)
    assert body["bets_reversed"] == 1
    assert await _balance(alice_w) == Decimal("60.0000")  # back to post-placement
    assert resolver.reopened == [m.id]
