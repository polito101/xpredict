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
from app.core.audit.models import AuditLog
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
from app.wallet.service import WalletService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from app.markets.models import Market

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
    """In-memory ``MarketResolvePort`` — records resolutions + reopenings (no markets
    table on this branch)."""

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


class RaisingMarketResolver:
    """A ``MarketResolvePort`` that fails — injects a mid-transaction error for the
    atomicity tests. The failing port method is called LAST in resolve/reverse, so by the
    time it raises the ledger postings + bet-status flips have already happened in the tx;
    the rollback must undo ALL of them (SC#5/#8)."""

    async def mark_resolved(
        self,
        session,
        *,
        market_id: UUID,
        winning_outcome_id: UUID,
        resolution_source: str,
        justification: str,
    ) -> None:
        raise RuntimeError("injected resolver failure")

    async def mark_unresolved(self, session, *, market_id: UUID) -> None:
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
    """Create a LEDGER-BACKED user_wallet at ``balance`` (committed); return (user_id, wallet_id).

    INSERTs the wallet at balance 0, then funds it to ``balance`` via the real
    ``WalletService.recharge`` (``house_promo -> wallet``, a proper ledger entry). A bare-balance
    INSERT — the older shortcut this helper used to be — leaves an orphan balance with no
    offsetting entry, which the production reconciler flags as drift the moment it runs. Since
    the testcontainer is session-scoped, that committed orphan also leaks into other suites'
    DB-wide ledger-integrity gate; seeding through the ledger keeps every suite green regardless
    of file ordering. The house singletons are snapshotted AFTER seeding in each test, so the
    funding recharge falls outside the before/after deltas.
    """
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


async def _resolve(
    session,
    *,
    market_id: UUID,
    winning_outcome_id: UUID,
    market_resolver,
    actor_user_id: UUID | None = None,
    justification: str = "resolved for test",
):
    """Call ``SettlementService.resolve_market`` with a default justification (SC#5 makes it
    mandatory). Tests that assert on the audit justification pass it explicitly."""
    return await SettlementService.resolve_market(
        session,
        market_id=market_id,
        winning_outcome_id=winning_outcome_id,
        market_resolver=market_resolver,
        actor_user_id=actor_user_id,
        justification=justification,
    )


async def _seed_real_market(market: MarketView) -> None:
    """INSERT a real ``markets`` row (+ its outcomes) matching ``market`` so the REAL
    ``HouseMarketResolveAdapter`` can persist the STL-06 resolution columns on it.

    The in-memory ``MarketView`` drives bet placement; this committed row is what the
    adapter UPDATEs (winning_outcome_id / resolution_source / resolution_justification).
    """
    from app.markets.enums import MarketSourceEnum, MarketStatus
    from app.markets.models import Market, Outcome

    sm = _get_session_maker()
    async with sm() as s, s.begin():
        mkt = Market(
            id=market.id,
            question=f"STL-06 persist {market.id.hex[:8]}",
            slug=f"stl06-persist-{market.id.hex[:8]}",
            resolution_criteria="test",
            source=MarketSourceEnum.HOUSE.value,
            status=MarketStatus.OPEN.value,
            deadline=market.deadline,
        )
        s.add(mkt)
        await s.flush()
        for ov in market.outcomes:
            s.add(
                Outcome(
                    id=ov.id,
                    market_id=market.id,
                    label=ov.label,
                    initial_odds=ov.price,
                    current_odds=ov.price,
                )
            )


async def _market_row(market_id: UUID) -> Market:
    from app.markets.models import Market

    sm = _get_session_maker()
    async with sm() as s:
        return (await s.execute(select(Market).where(Market.id == market_id))).scalar_one()


async def _audit_for_market(event_type: str, market_id: UUID) -> list[AuditLog]:
    """Audit rows of ``event_type`` whose payload ``market_id`` matches (committed state)."""
    sm = _get_session_maker()
    async with sm() as s:
        return list(
            (
                await s.execute(
                    select(AuditLog).where(
                        AuditLog.event_type == event_type,
                        AuditLog.payload["market_id"].astext == str(market_id),
                    )
                )
            )
            .scalars()
            .all()
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
        plan = await _resolve(
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
# STL-06 — the REAL adapter persists winner + source + justification on the markets
# row inside the settlement tx (admin path => "HOUSE", system path => "POLYMARKET_UMA").
# --------------------------------------------------------------------------- #
async def test_resolve_market_persists_resolution_columns_house() -> None:
    from app.settlement.adapters import HouseMarketResolveAdapter

    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN))
    yes, no = m.outcomes
    await _seed_real_market(m)  # a real markets row the adapter can UPDATE
    alice, _ = await _seed_wallet(Decimal("100.0000"))
    bob, _ = await _seed_wallet(Decimal("100.0000"))
    await _place(alice, m, yes.id, Decimal("40.0000"), src)  # winner
    await _place(bob, m, no.id, Decimal("60.0000"), src)  # loser
    admin_id = uuid4()

    sm = _get_session_maker()
    async with sm() as session:
        await _resolve(
            session,
            market_id=m.id,
            winning_outcome_id=yes.id,
            market_resolver=HouseMarketResolveAdapter(),
            actor_user_id=admin_id,  # admin path => HOUSE token
            justification="YES per the official source",
        )

    row = await _market_row(m.id)
    assert row.status == "RESOLVED"
    assert row.winning_outcome_id == yes.id
    assert row.resolution_source == "HOUSE"  # actor_user_id set => admin/house resolve
    assert row.resolution_justification == "YES per the official source"
    assert row.resolved_at is not None


async def test_resolve_market_persists_polymarket_uma_source_when_no_actor() -> None:
    from app.settlement.adapters import HouseMarketResolveAdapter

    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN))
    yes, _no = m.outcomes
    await _seed_real_market(m)
    alice, _ = await _seed_wallet(Decimal("100.0000"))
    await _place(alice, m, yes.id, Decimal("20.0000"), src)

    sm = _get_session_maker()
    async with sm() as session:
        await _resolve(
            session,
            market_id=m.id,
            winning_outcome_id=yes.id,
            market_resolver=HouseMarketResolveAdapter(),
            actor_user_id=None,  # system path => POLYMARKET_UMA token
            justification="auto-resolved from Polymarket UMA",
        )

    row = await _market_row(m.id)
    assert row.winning_outcome_id == yes.id
    assert row.resolution_source == "POLYMARKET_UMA"  # actor None => auto/Polymarket path
    assert row.resolution_justification == "auto-resolved from Polymarket UMA"


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
        await _resolve(s1, market_id=m.id, winning_outcome_id=yes.id, market_resolver=resolver)
    alice_after_first = await _balance(alice_w)
    promo_after_first = await _balance(HOUSE_PROMO_ACCOUNT_ID)
    revenue_after_first = await _balance(HOUSE_REVENUE_ACCOUNT_ID)

    # Resolve AGAIN — the bets are no longer PENDING, so nothing is settled.
    async with sm() as s2:
        plan2 = await _resolve(
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
            await _resolve(
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
        plan = await _resolve(
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
        plan = await _resolve(
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
        plan = await _resolve(
            session,
            market_id=market_id,
            winning_outcome_id=winning_outcome_id,
            market_resolver=resolver,
        )
    assert plan.settled == ()
    assert plan.total_payout == Decimal("0")
    assert resolver.resolved == [(market_id, winning_outcome_id)]


# --------------------------------------------------------------------------- #
# Audit (SC#5) — resolve writes ONE immutable audit_log row inside the same tx.
# --------------------------------------------------------------------------- #
async def test_resolve_market_writes_settlement_audit() -> None:
    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN))
    yes, no = m.outcomes
    alice, _ = await _seed_wallet(Decimal("100.0000"))
    bob, _ = await _seed_wallet(Decimal("100.0000"))
    await _place(alice, m, yes.id, Decimal("40.0000"), src)  # winner
    await _place(bob, m, no.id, Decimal("60.0000"), src)  # loser
    admin_id = uuid4()

    resolver = FakeMarketResolver()
    sm = _get_session_maker()
    async with sm() as session:
        await _resolve(
            session,
            market_id=m.id,
            winning_outcome_id=yes.id,
            market_resolver=resolver,
            actor_user_id=admin_id,
            justification="YES per the official source",
        )

    rows = await _audit_for_market("settlement.resolved", m.id)
    assert len(rows) == 1
    audit = rows[0]
    assert audit.actor == f"user:{admin_id}"
    payload = audit.payload
    assert payload["market_id"] == str(m.id)
    assert payload["winning_outcome"] == str(yes.id)
    assert payload["resolver"] == str(admin_id)
    assert payload["justification"] == "YES per the official source"
    # Money is a STRING in the audit payload, never a JSON float (SC#4 discipline).
    assert payload["total_payout"] == "80.0000"


# --------------------------------------------------------------------------- #
# Reversal (SC#8) — compensating entries restore the exact pre-settlement state.
# --------------------------------------------------------------------------- #
async def test_reverse_settlement_restores_pre_settlement_state() -> None:
    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN))
    yes, no = m.outcomes
    alice, alice_w = await _seed_wallet(Decimal("100.0000"))
    bob, bob_w = await _seed_wallet(Decimal("100.0000"))
    await _place(alice, m, yes.id, Decimal("40.0000"), src)  # winner
    await _place(bob, m, no.id, Decimal("60.0000"), src)  # loser
    liability = await _liability_id(m.id)

    # Snapshot the post-placement state — reversal must return to EXACTLY this.
    promo_pre = await _balance(HOUSE_PROMO_ACCOUNT_ID)
    revenue_pre = await _balance(HOUSE_REVENUE_ACCOUNT_ID)
    assert await _balance(alice_w) == Decimal("60.0000")
    assert await _balance(bob_w) == Decimal("40.0000")
    assert await _balance(liability) == Decimal("100.0000")

    resolver = FakeMarketResolver()
    sm = _get_session_maker()
    async with sm() as s:
        await _resolve(s, market_id=m.id, winning_outcome_id=yes.id, market_resolver=resolver)
    assert await _balance(alice_w) == Decimal("140.0000")  # settled

    # Reverse the settlement.
    async with sm() as s:
        count = await SettlementService.reverse_settlement(
            s,
            market_id=m.id,
            market_resolver=resolver,
            justification="resolved against the wrong source",
            actor_user_id=uuid4(),
        )

    assert count == 2
    # Every balance is restored to the pre-settlement snapshot.
    assert await _balance(alice_w) == Decimal("60.0000")
    assert await _balance(bob_w) == Decimal("40.0000")
    assert await _balance(liability) == Decimal("100.0000")
    assert await _balance(HOUSE_PROMO_ACCOUNT_ID) == promo_pre
    assert await _balance(HOUSE_REVENUE_ACCOUNT_ID) == revenue_pre
    # Bets walk back SETTLED -> PENDING; the market is reopened.
    assert (await _bets_for_user(alice))[0].status == BET_PENDING
    assert (await _bets_for_user(bob))[0].status == BET_PENDING
    assert resolver.reopened == [m.id]


async def test_reverse_settlement_writes_audit() -> None:
    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN))
    yes, no = m.outcomes
    alice, _ = await _seed_wallet(Decimal("100.0000"))
    await _place(alice, m, yes.id, Decimal("40.0000"), src)
    admin_id = uuid4()

    resolver = FakeMarketResolver()
    sm = _get_session_maker()
    async with sm() as s:
        await _resolve(s, market_id=m.id, winning_outcome_id=yes.id, market_resolver=resolver)
    async with sm() as s:
        await SettlementService.reverse_settlement(
            s,
            market_id=m.id,
            market_resolver=resolver,
            justification="data feed was wrong",
            actor_user_id=admin_id,
        )

    rows = await _audit_for_market("settlement.reversed", m.id)
    assert len(rows) == 1
    audit = rows[0]
    assert audit.actor == f"user:{admin_id}"
    assert audit.payload["justification"] == "data feed was wrong"
    assert audit.payload["bets_reversed"] == 1


async def test_reverse_settlement_is_idempotent() -> None:
    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN))
    yes, no = m.outcomes
    alice, alice_w = await _seed_wallet(Decimal("100.0000"))
    await _place(alice, m, yes.id, Decimal("40.0000"), src)

    resolver = FakeMarketResolver()
    sm = _get_session_maker()
    async with sm() as s:
        await _resolve(s, market_id=m.id, winning_outcome_id=yes.id, market_resolver=resolver)
    async with sm() as s:
        await SettlementService.reverse_settlement(
            s, market_id=m.id, market_resolver=resolver, justification="first reversal"
        )
    restored = await _balance(alice_w)

    # Reverse AGAIN — no SETTLED bets remain, so it is a no-op (no double-refund).
    async with sm() as s:
        count2 = await SettlementService.reverse_settlement(
            s, market_id=m.id, market_resolver=resolver, justification="second reversal"
        )
    assert count2 == 0
    assert await _balance(alice_w) == restored


async def test_reverse_settlement_is_atomic_on_failure() -> None:
    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN))
    yes, no = m.outcomes
    alice, alice_w = await _seed_wallet(Decimal("100.0000"))
    await _place(alice, m, yes.id, Decimal("40.0000"), src)

    resolver = FakeMarketResolver()
    sm = _get_session_maker()
    async with sm() as s:
        await _resolve(s, market_id=m.id, winning_outcome_id=yes.id, market_resolver=resolver)
    settled_balance = await _balance(alice_w)  # 140

    # The reversal fails at the market-reopen step AFTER the compensating postings; the
    # whole tx must roll back, leaving the settled state intact.
    with pytest.raises(RuntimeError):
        async with sm() as s:
            await SettlementService.reverse_settlement(
                s,
                market_id=m.id,
                market_resolver=RaisingMarketResolver(),
                justification="will fail",
            )

    assert await _balance(alice_w) == settled_balance  # unchanged (still settled)
    assert (await _bets_for_user(alice))[0].status == BET_SETTLED_WON


# --------------------------------------------------------------------------- #
# Defensive status guard (adapters.py). The markets row has no resolve guard of its own
# and SettlementService calls mark_resolved OUTSIDE its `if bets:` block, so the status
# flip lands even when no money moves. Two terminal states must be handled:
#   - CANCELLED: a voided market must NEVER be force-RESOLVED (it would force win/loss
#     payouts on a voided event). Hard error — no production path resolves a CANCELLED
#     market today (the enum has no writer).
#   - RESOLVED: tolerate idempotently. Re-resolve is the EVA-03 event-replay canary; the
#     bet-status PENDING filter is the ledger-side guard. Skip — never re-stamp the winner
#     / resolved_at, and never RAISE (raising would fail every child of an idempotent
#     resolve_event replay -> test_resolve_event_is_idempotent).
# --------------------------------------------------------------------------- #
async def _seed_market_with_status(status: str) -> tuple[UUID, UUID, UUID]:
    """INSERT a real ``markets`` row (+ YES/NO outcomes) in ``status``; return
    ``(market_id, yes_id, no_id)``. The REAL adapter UPDATEs this committed row.

    Mirrors ``_seed_real_market`` (same required columns) but parametrizes the status so a
    terminal-state row can be seeded directly."""
    from app.markets.enums import MarketSourceEnum
    from app.markets.models import Market, Outcome

    market_id, yes_id, no_id = uuid4(), uuid4(), uuid4()
    sm = _get_session_maker()
    async with sm() as s, s.begin():
        s.add(
            Market(
                id=market_id,
                question=f"guard {market_id.hex[:8]}",
                slug=f"guard-{market_id.hex[:8]}",
                resolution_criteria="test",
                source=MarketSourceEnum.HOUSE.value,
                status=status,
                deadline=datetime.now(UTC) + timedelta(days=1),
            )
        )
        await s.flush()
        s.add_all(
            [
                Outcome(
                    id=yes_id,
                    market_id=market_id,
                    label="YES",
                    initial_odds=Decimal("0.5"),
                    current_odds=Decimal("0.5"),
                ),
                Outcome(
                    id=no_id,
                    market_id=market_id,
                    label="NO",
                    initial_odds=Decimal("0.5"),
                    current_odds=Decimal("0.5"),
                ),
            ]
        )
    return market_id, yes_id, no_id


async def test_mark_resolved_rejects_cancelled_market() -> None:
    """A CANCELLED (voided) market must never be force-RESOLVED — that would force
    win/loss payouts on a voided event. Pure defense: no production path resolves a
    CANCELLED market today, so this guards a future cancel feature wiring it up before a
    stake-refund path exists (none does — settlement/event_service.py void_event)."""
    from app.settlement.adapters import HouseMarketResolveAdapter

    market_id, yes_id, _no_id = await _seed_market_with_status("CANCELLED")

    sm = _get_session_maker()
    async with sm() as s:
        with pytest.raises(ValueError, match="CANCELLED"):
            await HouseMarketResolveAdapter().mark_resolved(
                s,
                market_id=market_id,
                winning_outcome_id=yes_id,
                resolution_source="HOUSE",
                justification="should be rejected",
            )

    row = await _market_row(market_id)
    assert row.status == "CANCELLED"  # untouched
    assert row.winning_outcome_id is None  # no winner stamped


async def test_mark_resolved_is_idempotent_on_already_resolved() -> None:
    """Re-resolving an already-RESOLVED market is a no-op: it must NOT raise (the EVA-03
    idempotent resolve_event replay calls mark_resolved on already-RESOLVED children) and
    must NOT overwrite the recorded winner or re-stamp resolved_at."""
    from app.markets.models import Market
    from app.settlement.adapters import HouseMarketResolveAdapter

    market_id, yes_id, no_id = await _seed_market_with_status("RESOLVED")

    # Stamp the original winner (YES) + a fixed resolved_at, as the first resolve would have.
    sm = _get_session_maker()
    async with sm() as s, s.begin():
        m = await s.get(Market, market_id)
        m.winning_outcome_id = yes_id
        m.resolved_at = datetime(2020, 1, 1, tzinfo=UTC)
    original_resolved_at = (await _market_row(market_id)).resolved_at

    # Re-resolve with a DIFFERENT winner (NO) — must be silently ignored, not overwrite.
    async with sm() as s, s.begin():
        await HouseMarketResolveAdapter().mark_resolved(
            s,
            market_id=market_id,
            winning_outcome_id=no_id,  # different from the stamped YES
            resolution_source="HOUSE",
            justification="idempotent replay",
        )

    row = await _market_row(market_id)
    assert row.status == "RESOLVED"
    assert row.winning_outcome_id == yes_id  # original winner preserved, NOT overwritten
    assert row.resolved_at == original_resolved_at  # not re-stamped
