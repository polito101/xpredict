"""BetService.place_bet — the atomic bet-placement core (Phase 5, SC#1 + SC#3 part).

Integration tests (testcontainers). The ``bets`` table is created via a fixture
(``Bet.__table__.create``) — its alembic migration ``0005`` is deferred to integration,
so this slice stays migration-free. Uses the committed-session pattern (own
``_get_session_maker()`` sessions) like ``test_recharge.py``, because ``place_bet`` owns
its own ``session.begin()`` unit of work.

Covered:
  - happy path: wallet debited, per-market liability credited, Bet PENDING, one
    ``bet_placed`` transfer + debit/credit pair;
  - the per-market liability account is created once and REUSED by later bets;
  - rejections (no money moved): market CLOSED, past deadline, unknown market,
    invalid outcome, insufficient balance, non-positive stake;
  - **atomicity (SC#1):** a failure after the bet INSERT rolls EVERYTHING back —
    neither the bet nor any ledger entry persists, balance unchanged.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.bets.constants import BET_PENDING, KIND_MARKET_LIABILITY, TRANSFER_BET_PLACED
from app.bets.exceptions import InvalidOutcome, MarketClosed, MarketNotFound, StakeOutOfRange
from app.bets.market_port import MARKET_CLOSED, MARKET_OPEN, MarketView, OutcomeView
from app.bets.models import Bet
from app.bets.service import BetService
from app.db.session import _get_session_maker
from app.wallet.constants import (
    DIRECTION_CREDIT,
    DIRECTION_DEBIT,
    KIND_USER_WALLET,
    OWNER_MARKET,
    OWNER_USER,
    PLAY_USD,
)
from app.wallet.exceptions import InsufficientBalance
from app.wallet.models import Account, Entry, Transfer
from app.wallet.service import WalletService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine:
    """Depend on ``engine`` (container, migrate, env rewrite) — mirrors test_recharge.py."""
    return engine


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _bets_table(engine: AsyncEngine):
    """Create the ``bets`` table (DDL ships in migration 0005; created here for tests)."""
    async with engine.begin() as conn:
        await conn.run_sync(Bet.__table__.create, checkfirst=True)
    yield


# --------------------------------------------------------------------------- #
# Stub market source (controllable, no DB) + builders.
# --------------------------------------------------------------------------- #
class StubMarketSource:
    def __init__(self) -> None:
        self._markets: dict[UUID, MarketView] = {}

    def add(self, market: MarketView) -> MarketView:
        self._markets[market.id] = market
        return market

    async def get_market(self, market_id: UUID) -> MarketView | None:
        return self._markets.get(market_id)


def _market(
    status: str = MARKET_OPEN,
    *,
    deadline: datetime | None = None,
    yes_price: Decimal = Decimal("0.5"),
    no_price: Decimal = Decimal("0.5"),
    min_stake: Decimal | None = None,
    max_stake: Decimal | None = None,
) -> MarketView:
    return MarketView(
        id=uuid4(),
        status=status,
        deadline=deadline or (datetime.now(UTC) + timedelta(days=1)),
        outcomes=(
            OutcomeView(id=uuid4(), label="YES", price=yes_price),
            OutcomeView(id=uuid4(), label="NO", price=no_price),
        ),
        min_stake=min_stake,
        max_stake=max_stake,
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


async def _entries_for_transfer(transfer_id: UUID) -> list[Entry]:
    sm = _get_session_maker()
    async with sm() as s:
        return list(
            (await s.execute(select(Entry).where(Entry.transfer_id == transfer_id))).scalars().all()
        )


async def _bet_placed_transfer_ids() -> set[UUID]:
    sm = _get_session_maker()
    async with sm() as s:
        rows = (
            await s.execute(select(Transfer.id).where(Transfer.kind == TRANSFER_BET_PLACED))
        ).scalars()
        return set(rows)


# --------------------------------------------------------------------------- #
# 1) Happy path
# --------------------------------------------------------------------------- #
async def test_place_bet_moves_stake_and_records_bet() -> None:
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN))
    yes = m.outcomes[0]
    stake = Decimal("30.0000")

    before = await _bet_placed_transfer_ids()
    sm = _get_session_maker()
    async with sm() as session:
        await BetService.place_bet(
            session,
            user_id=user_id,
            market_id=m.id,
            outcome_id=yes.id,
            stake=stake,
            market_source=src,
        )

    # Wallet debited by the stake; per-market liability credited by the stake.
    assert await _balance(wallet_id) == Decimal("70.0000")
    liability_id = await _liability_id(m.id)
    assert liability_id is not None
    assert await _balance(liability_id) == stake

    # Exactly one PENDING bet on the chosen outcome.
    bets = await _bets_for_user(user_id)
    assert len(bets) == 1
    assert bets[0].status == BET_PENDING
    assert bets[0].outcome_id == yes.id
    assert bets[0].stake == stake

    # One new bet_placed transfer with a debit(wallet)+credit(liability) pair.
    after = await _bet_placed_transfer_ids()
    new_ids = after - before
    assert len(new_ids) == 1
    entries = await _entries_for_transfer(next(iter(new_ids)))
    assert {e.direction for e in entries} == {DIRECTION_DEBIT, DIRECTION_CREDIT}
    debit = next(e for e in entries if e.direction == DIRECTION_DEBIT)
    credit = next(e for e in entries if e.direction == DIRECTION_CREDIT)
    assert debit.account_id == wallet_id
    assert credit.account_id == liability_id
    assert debit.amount == stake


# --------------------------------------------------------------------------- #
# 1b) Odds locked at placement (the Phase 4 odds seam) — captured on the bet
# --------------------------------------------------------------------------- #
async def test_place_bet_captures_odds_at_placement() -> None:
    """The chosen outcome's price (Phase 4 ``current_odds``) is locked onto the bet.

    Settlement later pays a winner ``stake / odds_at_placement`` — so the price MUST be
    captured at placement (the "odds locked at placement" model), not re-read at
    resolution when odds may have moved.
    """
    user_id, _ = await _seed_wallet(Decimal("100.0000"))
    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN, yes_price=Decimal("0.4"), no_price=Decimal("0.6")))
    yes = m.outcomes[0]
    sm = _get_session_maker()
    async with sm() as session:
        await BetService.place_bet(
            session,
            user_id=user_id,
            market_id=m.id,
            outcome_id=yes.id,
            stake=Decimal("30.0000"),
            market_source=src,
        )

    bets = await _bets_for_user(user_id)
    assert len(bets) == 1
    assert bets[0].outcome_id == yes.id
    assert bets[0].odds_at_placement == Decimal("0.4")  # locked YES price, not NO's 0.6


# --------------------------------------------------------------------------- #
# 2) The per-market liability account is created once and reused
# --------------------------------------------------------------------------- #
async def test_second_bet_reuses_market_liability_account() -> None:
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN))
    sm = _get_session_maker()
    async with sm() as s1:
        await BetService.place_bet(
            s1,
            user_id=user_id,
            market_id=m.id,
            outcome_id=m.outcomes[0].id,
            stake=Decimal("10.0000"),
            market_source=src,
        )
    liability_first = await _liability_id(m.id)
    async with sm() as s2:
        await BetService.place_bet(
            s2,
            user_id=user_id,
            market_id=m.id,
            outcome_id=m.outcomes[1].id,
            stake=Decimal("15.0000"),
            market_source=src,
        )
    liability_second = await _liability_id(m.id)

    assert liability_first == liability_second  # same account, not duplicated
    assert await _balance(liability_first) == Decimal("25.0000")  # 10 + 15
    assert await _balance(wallet_id) == Decimal("75.0000")
    assert len(await _bets_for_user(user_id)) == 2


# --------------------------------------------------------------------------- #
# 3) Rejections — no money moves, no bet recorded
# --------------------------------------------------------------------------- #
async def test_place_bet_rejected_when_market_closed() -> None:
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    src = StubMarketSource()
    m = src.add(_market(MARKET_CLOSED))
    sm = _get_session_maker()
    with pytest.raises(MarketClosed):
        async with sm() as session:
            await BetService.place_bet(
                session,
                user_id=user_id,
                market_id=m.id,
                outcome_id=m.outcomes[0].id,
                stake=Decimal("10.0000"),
                market_source=src,
            )
    assert await _balance(wallet_id) == Decimal("100.0000")
    assert await _bets_for_user(user_id) == []


async def test_place_bet_rejected_past_deadline() -> None:
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN, deadline=datetime.now(UTC) - timedelta(minutes=1)))
    sm = _get_session_maker()
    with pytest.raises(MarketClosed):
        async with sm() as session:
            await BetService.place_bet(
                session,
                user_id=user_id,
                market_id=m.id,
                outcome_id=m.outcomes[0].id,
                stake=Decimal("10.0000"),
                market_source=src,
            )
    assert await _balance(wallet_id) == Decimal("100.0000")


async def test_place_bet_rejected_unknown_market() -> None:
    user_id, _ = await _seed_wallet(Decimal("100.0000"))
    src = StubMarketSource()  # empty
    sm = _get_session_maker()
    with pytest.raises(MarketNotFound):
        async with sm() as session:
            await BetService.place_bet(
                session,
                user_id=user_id,
                market_id=uuid4(),
                outcome_id=uuid4(),
                stake=Decimal("10.0000"),
                market_source=src,
            )


async def test_place_bet_rejected_invalid_outcome() -> None:
    user_id, _ = await _seed_wallet(Decimal("100.0000"))
    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN))
    sm = _get_session_maker()
    with pytest.raises(InvalidOutcome):
        async with sm() as session:
            await BetService.place_bet(
                session,
                user_id=user_id,
                market_id=m.id,
                outcome_id=uuid4(),  # not an outcome of m
                stake=Decimal("10.0000"),
                market_source=src,
            )


async def test_place_bet_rejected_insufficient_balance() -> None:
    user_id, wallet_id = await _seed_wallet(Decimal("5.0000"))
    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN))
    sm = _get_session_maker()
    with pytest.raises(InsufficientBalance):
        async with sm() as session:
            await BetService.place_bet(
                session,
                user_id=user_id,
                market_id=m.id,
                outcome_id=m.outcomes[0].id,
                stake=Decimal("10.0000"),
                market_source=src,
            )
    assert await _balance(wallet_id) == Decimal("5.0000")
    assert await _bets_for_user(user_id) == []


async def test_place_bet_rejected_nonpositive_stake() -> None:
    user_id, _ = await _seed_wallet(Decimal("100.0000"))
    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN))
    sm = _get_session_maker()
    with pytest.raises(ValueError):
        async with sm() as session:
            await BetService.place_bet(
                session,
                user_id=user_id,
                market_id=m.id,
                outcome_id=m.outcomes[0].id,
                stake=Decimal("0"),
                market_source=src,
            )


# --------------------------------------------------------------------------- #
# 3b) Per-market stake limits (BET-06) — per-market bounds preferred; NULL -> global
# --------------------------------------------------------------------------- #
async def test_place_bet_rejects_below_per_market_min_preferring_market_over_config() -> None:
    """A per-market min_stake=10 rejects a stake of 5 (above the global min of 1) — the
    per-market bound is PREFERRED over the global config; no money moves, no bet recorded."""
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN, min_stake=Decimal("10"), max_stake=Decimal("50")))
    sm = _get_session_maker()
    with pytest.raises(StakeOutOfRange):
        async with sm() as session:
            await BetService.place_bet(
                session,
                user_id=user_id,
                market_id=m.id,
                outcome_id=m.outcomes[0].id,
                stake=Decimal("5.0000"),  # above global min (1) but below per-market min (10)
                market_source=src,
            )
    assert await _balance(wallet_id) == Decimal("100.0000")
    assert await _bets_for_user(user_id) == []


async def test_place_bet_rejects_above_per_market_max_preferring_market_over_config() -> None:
    """A per-market max_stake=50 rejects a stake of 60 (far below the global max of 100000)."""
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN, min_stake=Decimal("10"), max_stake=Decimal("50")))
    sm = _get_session_maker()
    with pytest.raises(StakeOutOfRange):
        async with sm() as session:
            await BetService.place_bet(
                session,
                user_id=user_id,
                market_id=m.id,
                outcome_id=m.outcomes[0].id,
                stake=Decimal("60.0000"),  # below global max (100000) but above per-market max (50)
                market_source=src,
            )
    assert await _balance(wallet_id) == Decimal("100.0000")
    assert await _bets_for_user(user_id) == []


async def test_place_bet_accepts_within_per_market_range() -> None:
    """A stake of 25 inside the per-market [10, 50] range is accepted and moves money."""
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN, min_stake=Decimal("10"), max_stake=Decimal("50")))
    sm = _get_session_maker()
    async with sm() as session:
        await BetService.place_bet(
            session,
            user_id=user_id,
            market_id=m.id,
            outcome_id=m.outcomes[0].id,
            stake=Decimal("25.0000"),
            market_source=src,
        )
    assert await _balance(wallet_id) == Decimal("75.0000")
    assert len(await _bets_for_user(user_id)) == 1


async def test_place_bet_null_market_limits_fall_back_to_global_config() -> None:
    """A market with NULL min/max_stake uses the global BET_MIN_STAKE/BET_MAX_STAKE: a stake
    BELOW the global min is rejected, and a stake just at the global min is accepted — proving
    the fallback path reads the config (no behavior change for existing NULL-limit markets)."""
    from app.core.config import get_settings

    cfg = get_settings()
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN))  # NULL min/max -> global fallback

    # Below the global min -> rejected via the fallback (no per-market bound set).
    sm = _get_session_maker()
    below = cfg.BET_MIN_STAKE / Decimal("2")  # 0.5 by default, < global min (1)
    with pytest.raises(StakeOutOfRange):
        async with sm() as session:
            await BetService.place_bet(
                session,
                user_id=user_id,
                market_id=m.id,
                outcome_id=m.outcomes[0].id,
                stake=below,
                market_source=src,
            )
    assert await _balance(wallet_id) == Decimal("100.0000")
    assert await _bets_for_user(user_id) == []

    # Exactly at the global min -> accepted (the fallback bound is inclusive).
    async with sm() as session:
        await BetService.place_bet(
            session,
            user_id=user_id,
            market_id=m.id,
            outcome_id=m.outcomes[0].id,
            stake=cfg.BET_MIN_STAKE,
            market_source=src,
        )
    assert len(await _bets_for_user(user_id)) == 1


# --------------------------------------------------------------------------- #
# 4) Atomicity (SC#1) — a failure after the bet INSERT rolls everything back
# --------------------------------------------------------------------------- #
async def test_place_bet_is_atomic_on_mid_transaction_failure(monkeypatch) -> None:
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    src = StubMarketSource()
    m = src.add(_market(MARKET_OPEN))

    async def _boom(*args, **kwargs):
        raise RuntimeError("injected mid-transaction failure")

    # Fail at the ledger step, AFTER the bet row has been inserted+flushed.
    monkeypatch.setattr(WalletService, "_post_transfer", _boom)

    sm = _get_session_maker()
    with pytest.raises(RuntimeError):
        async with sm() as session:
            await BetService.place_bet(
                session,
                user_id=user_id,
                market_id=m.id,
                outcome_id=m.outcomes[0].id,
                stake=Decimal("10.0000"),
                market_source=src,
            )

    # Nothing persisted: balance unchanged, no bet, no liability credit.
    assert await _balance(wallet_id) == Decimal("100.0000")
    assert await _bets_for_user(user_id) == []
    liability_id = await _liability_id(m.id)
    if liability_id is not None:  # the empty account may exist (created pre-tx); credit must be 0
        assert await _balance(liability_id) == Decimal("0.0000")
