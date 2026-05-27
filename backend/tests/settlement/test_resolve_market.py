"""SettlementService.resolve_market — the transactional settlement pass (Phase 5, SC#5/#6).

Integration tests (testcontainers). Mirrors ``test_place_bet.py``: the ``bets`` table is
created via a fixture (migration ``0005`` is deferred to integration), the committed-session
pattern (own ``_get_session_maker()`` sessions) is used because ``resolve_market`` owns its
``session.begin()``, and the ``house_promo`` / ``house_revenue`` singletons come from migration
``0003`` (seeded by ``alembic upgrade head`` in the ``engine`` fixture).

Because the testcontainer is session-scoped, committed writes persist across tests; the SHARED
house singletons therefore use before/after DELTAS, while per-test wallets and the per-market
liability use fresh UUIDs and assert absolute values.

Covered:
  - happy path: a winner is paid ``stake / price`` (stake back from the market liability +
    winnings from ``house_promo``), a loser's stake is swept to ``house_revenue``, the liability
    nets to zero, bets flip ``PENDING`` -> ``SETTLED_WON`` / ``SETTLED_LOST``, and the market is
    marked RESOLVED in the SAME ACID transaction.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.bets.constants import (
    BET_PENDING,
    BET_SETTLED_LOST,
    BET_SETTLED_WON,
    KIND_MARKET_LIABILITY,
)
from app.bets.market_port import MARKET_OPEN, MarketView, OutcomeView
from app.bets.models import Bet
from app.bets.service import BetService
from app.db.session import _get_session_maker
from app.settlement.service import SettlementService
from app.wallet.constants import (
    HOUSE_PROMO_ACCOUNT_ID,
    HOUSE_REVENUE_ACCOUNT_ID,
    KIND_USER_WALLET,
    OWNER_MARKET,
    OWNER_USER,
    PLAY_USD,
)
from app.wallet.models import Account

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine:
    """Depend on ``engine`` (container, migrate, env rewrite) — mirrors test_place_bet.py."""
    return engine


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _bets_table(engine: AsyncEngine):
    """Create the ``bets`` table (DDL ships in migration 0005; created here for tests)."""
    async with engine.begin() as conn:
        await conn.run_sync(Bet.__table__.create, checkfirst=True)
    yield


# --------------------------------------------------------------------------- #
# Stub market source (for placement) + fake resolver (the write port) + builders.
# --------------------------------------------------------------------------- #
class StubMarketSource:
    def __init__(self) -> None:
        self._markets: dict[UUID, MarketView] = {}

    def add(self, market: MarketView) -> MarketView:
        self._markets[market.id] = market
        return market

    async def get_market(self, market_id: UUID) -> MarketView | None:
        return self._markets.get(market_id)


class FakeMarketResolver:
    """In-memory ``MarketResolvePort`` — records resolutions (no markets table on this branch)."""

    def __init__(self) -> None:
        self.resolved: list[tuple[UUID, UUID]] = []

    async def mark_resolved(self, session, *, market_id: UUID, winning_outcome_id: UUID) -> None:
        self.resolved.append((market_id, winning_outcome_id))


class RaisingMarketResolver:
    """A ``MarketResolvePort`` that fails — injects a mid-transaction error for the
    atomicity test. Called LAST in ``resolve_market``, so by the time it raises the
    ledger postings + bet-status flips have already happened in the tx; the rollback
    must undo ALL of them (SC#5)."""

    async def mark_resolved(self, session, *, market_id: UUID, winning_outcome_id: UUID) -> None:
        raise RuntimeError("injected resolver failure")


def _market(
    status: str = MARKET_OPEN,
    *,
    deadline: datetime | None = None,
    yes_price: Decimal = Decimal("0.5"),
    no_price: Decimal = Decimal("0.5"),
) -> MarketView:
    return MarketView(
        id=uuid4(),
        status=status,
        deadline=deadline or (datetime.now(UTC) + timedelta(days=1)),
        outcomes=(
            OutcomeView(id=uuid4(), label="YES", price=yes_price),
            OutcomeView(id=uuid4(), label="NO", price=no_price),
        ),
    )


# --------------------------------------------------------------------------- #
# Committed-session helpers (assert against committed state).
# --------------------------------------------------------------------------- #
async def _seed_wallet(balance: Decimal) -> tuple[UUID, UUID]:
    """INSERT a user_wallet at ``balance`` (committed); return (user_id, wallet_id)."""
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
                "bal": balance,
            },
        )
    return user_id, wallet_id


async def _balance(account_id: UUID) -> Decimal:
    sm = _get_session_maker()
    async with sm() as s:
        return (
            await s.execute(select(Account.balance).where(Account.id == account_id))
        ).scalar_one()


async def _liability_id(market_id: UUID) -> UUID | None:
    sm = _get_session_maker()
    async with sm() as s:
        return (
            await s.execute(
                select(Account.id).where(
                    Account.owner_type == OWNER_MARKET,
                    Account.owner_id == market_id,
                    Account.kind == KIND_MARKET_LIABILITY,
                    Account.currency == PLAY_USD,
                )
            )
        ).scalar_one_or_none()


async def _bets_for_user(user_id: UUID) -> list[Bet]:
    sm = _get_session_maker()
    async with sm() as s:
        return list((await s.execute(select(Bet).where(Bet.user_id == user_id))).scalars().all())


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


# --------------------------------------------------------------------------- #
# Happy path — winners paid, losers swept, liability drained, bets flipped, market resolved.
# --------------------------------------------------------------------------- #
async def test_resolve_market_pays_winners_and_sweeps_losers() -> None:
    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN, yes_price=Decimal("0.5"), no_price=Decimal("0.5")))
    yes, no = m.outcomes
    alice, alice_w = await _seed_wallet(Decimal("100.0000"))
    bob, bob_w = await _seed_wallet(Decimal("100.0000"))
    await _place(alice, m, yes.id, Decimal("40.0000"), src)  # winner
    await _place(bob, m, no.id, Decimal("60.0000"), src)  # loser

    liability = await _liability_id(m.id)
    assert liability is not None
    assert await _balance(liability) == Decimal("100.0000")  # 40 + 60 staked

    promo_before = await _balance(HOUSE_PROMO_ACCOUNT_ID)
    revenue_before = await _balance(HOUSE_REVENUE_ACCOUNT_ID)

    resolver = FakeMarketResolver()
    sm = _get_session_maker()
    async with sm() as session:
        plan = await SettlementService.resolve_market(
            session,
            market_id=m.id,
            winning_outcome_id=yes.id,
            market_resolver=resolver,
        )

    # Alice (winner): 100 - 40 stake, then payout 40 / 0.5 = 80 credited -> 140.
    assert await _balance(alice_w) == Decimal("140.0000")
    # Bob (loser): 100 - 60 stake, nothing back -> 40.
    assert await _balance(bob_w) == Decimal("40.0000")
    # The per-market liability nets to zero (all stakes left it).
    assert await _balance(liability) == Decimal("0.0000")
    # house_revenue gained the loser's stake; house_promo funded the winner's winnings.
    assert await _balance(HOUSE_REVENUE_ACCOUNT_ID) - revenue_before == Decimal("60.0000")
    assert promo_before - await _balance(HOUSE_PROMO_ACCOUNT_ID) == Decimal("40.0000")
    # Bets walk PENDING -> SETTLED_WON / SETTLED_LOST.
    assert (await _bets_for_user(alice))[0].status == BET_SETTLED_WON
    assert (await _bets_for_user(bob))[0].status == BET_SETTLED_LOST
    # The market is marked RESOLVED in the same operation (write port).
    assert resolver.resolved == [(m.id, yes.id)]
    # The returned plan exposes the aggregate flows.
    assert plan.total_payout == Decimal("80.0000")
    assert plan.total_loser_stake == Decimal("60.0000")


# --------------------------------------------------------------------------- #
# Idempotency (SC#6) — re-resolving settles nothing (no double-credit).
# --------------------------------------------------------------------------- #
async def test_resolve_market_is_idempotent() -> None:
    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN))
    yes, no = m.outcomes
    alice, alice_w = await _seed_wallet(Decimal("100.0000"))
    bob, bob_w = await _seed_wallet(Decimal("100.0000"))
    await _place(alice, m, yes.id, Decimal("40.0000"), src)
    await _place(bob, m, no.id, Decimal("60.0000"), src)

    resolver = FakeMarketResolver()
    sm = _get_session_maker()
    async with sm() as s1:
        await SettlementService.resolve_market(
            s1, market_id=m.id, winning_outcome_id=yes.id, market_resolver=resolver
        )
    alice_after_first = await _balance(alice_w)
    promo_after_first = await _balance(HOUSE_PROMO_ACCOUNT_ID)
    revenue_after_first = await _balance(HOUSE_REVENUE_ACCOUNT_ID)

    # Resolve AGAIN — the bets are no longer PENDING, so nothing is settled.
    async with sm() as s2:
        plan2 = await SettlementService.resolve_market(
            s2, market_id=m.id, winning_outcome_id=yes.id, market_resolver=resolver
        )

    assert plan2.settled == ()  # no pending bets the second time
    assert await _balance(alice_w) == alice_after_first  # no double-credit
    assert await _balance(HOUSE_PROMO_ACCOUNT_ID) == promo_after_first
    assert await _balance(HOUSE_REVENUE_ACCOUNT_ID) == revenue_after_first


# --------------------------------------------------------------------------- #
# Atomicity (SC#5) — a mid-transaction failure rolls EVERYTHING back.
# --------------------------------------------------------------------------- #
async def test_resolve_market_is_atomic_on_failure() -> None:
    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN))
    yes, no = m.outcomes
    alice, alice_w = await _seed_wallet(Decimal("100.0000"))
    bob, bob_w = await _seed_wallet(Decimal("100.0000"))
    await _place(alice, m, yes.id, Decimal("40.0000"), src)
    await _place(bob, m, no.id, Decimal("60.0000"), src)

    liability = await _liability_id(m.id)
    promo_before = await _balance(HOUSE_PROMO_ACCOUNT_ID)
    revenue_before = await _balance(HOUSE_REVENUE_ACCOUNT_ID)

    sm = _get_session_maker()
    with pytest.raises(RuntimeError):
        async with sm() as session:
            await SettlementService.resolve_market(
                session,
                market_id=m.id,
                winning_outcome_id=yes.id,
                market_resolver=RaisingMarketResolver(),
            )

    # Nothing moved: wallets at their post-placement balances, liability intact,
    # house untouched, both bets still PENDING.
    assert await _balance(alice_w) == Decimal("60.0000")  # 100 - 40 stake (placement only)
    assert await _balance(bob_w) == Decimal("40.0000")  # 100 - 60 stake (placement only)
    assert await _balance(liability) == Decimal("100.0000")
    assert await _balance(HOUSE_PROMO_ACCOUNT_ID) == promo_before
    assert await _balance(HOUSE_REVENUE_ACCOUNT_ID) == revenue_before
    assert (await _bets_for_user(alice))[0].status == BET_PENDING
    assert (await _bets_for_user(bob))[0].status == BET_PENDING


# --------------------------------------------------------------------------- #
# Edge: price == 1.0 (certainty) — payout == stake, NO winnings leg, house untouched.
# --------------------------------------------------------------------------- #
async def test_resolve_market_certainty_pays_stake_only() -> None:
    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN, yes_price=Decimal("1.0")))
    yes, _no = m.outcomes
    alice, alice_w = await _seed_wallet(Decimal("100.0000"))
    await _place(alice, m, yes.id, Decimal("30.0000"), src)  # winner at price 1.0

    liability = await _liability_id(m.id)
    promo_before = await _balance(HOUSE_PROMO_ACCOUNT_ID)
    resolver = FakeMarketResolver()
    sm = _get_session_maker()
    async with sm() as session:
        plan = await SettlementService.resolve_market(
            session, market_id=m.id, winning_outcome_id=yes.id, market_resolver=resolver
        )

    # payout = 30 / 1.0 = 30 == stake -> wallet restored, no winnings leg funded.
    assert await _balance(alice_w) == Decimal("100.0000")
    assert await _balance(liability) == Decimal("0.0000")
    assert await _balance(HOUSE_PROMO_ACCOUNT_ID) == promo_before  # CHECK(amount>0) never tripped
    assert plan.total_payout == Decimal("30.0000")
    assert (await _bets_for_user(alice))[0].status == BET_SETTLED_WON


# --------------------------------------------------------------------------- #
# Edge: all bets lose — every stake is swept to house_revenue, house_promo untouched.
# --------------------------------------------------------------------------- #
async def test_resolve_market_all_losers_sweeps_to_house_revenue() -> None:
    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN))
    yes, no = m.outcomes
    alice, alice_w = await _seed_wallet(Decimal("100.0000"))
    await _place(alice, m, no.id, Decimal("25.0000"), src)  # bets NO; YES will win

    liability = await _liability_id(m.id)
    promo_before = await _balance(HOUSE_PROMO_ACCOUNT_ID)
    revenue_before = await _balance(HOUSE_REVENUE_ACCOUNT_ID)
    resolver = FakeMarketResolver()
    sm = _get_session_maker()
    async with sm() as session:
        plan = await SettlementService.resolve_market(
            session, market_id=m.id, winning_outcome_id=yes.id, market_resolver=resolver
        )

    assert await _balance(alice_w) == Decimal("75.0000")  # lost the 25 stake
    assert await _balance(liability) == Decimal("0.0000")
    assert await _balance(HOUSE_REVENUE_ACCOUNT_ID) - revenue_before == Decimal("25.0000")
    assert await _balance(HOUSE_PROMO_ACCOUNT_ID) == promo_before  # no winner funded
    assert plan.total_payout == Decimal("0")
    assert plan.total_loser_stake == Decimal("25.0000")
    assert (await _bets_for_user(alice))[0].status == BET_SETTLED_LOST


# --------------------------------------------------------------------------- #
# Edge: empty market — no bets, still marked resolved (the no-op resolve).
# --------------------------------------------------------------------------- #
async def test_resolve_empty_market_marks_resolved_only() -> None:
    market_id = uuid4()
    winning_outcome_id = uuid4()
    resolver = FakeMarketResolver()
    sm = _get_session_maker()
    async with sm() as session:
        plan = await SettlementService.resolve_market(
            session,
            market_id=market_id,
            winning_outcome_id=winning_outcome_id,
            market_resolver=resolver,
        )
    assert plan.settled == ()
    assert plan.total_payout == Decimal("0")
    assert resolver.resolved == [(market_id, winning_outcome_id)]
