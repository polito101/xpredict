"""BetService.sell_position — early-close (cash-out) at the live price (Task A2).

Integration tests (testcontainers). Mirrors ``test_resolve_market.py``: the ``bets`` table is
created via a fixture (migration ``0005`` is deferred to integration), the committed-session
pattern (own ``_get_session_maker()`` sessions) is used because ``sell_position`` owns its
``session.begin()``, and the ``house_promo`` / ``house_revenue`` singletons come from migration
``0003`` (seeded by ``alembic upgrade head`` in the ``engine`` fixture).

Because the testcontainer is session-scoped, committed writes persist across tests; the SHARED
house singletons therefore use before/after DELTAS, while per-test wallets and the per-market
liability use fresh UUIDs and assert absolute values.

Covered:
  - GAIN: payout above stake -> stake back from liability + winnings from ``house_promo``;
  - LOSS: payout below stake -> cash-out from liability + shortfall swept to ``house_revenue``;
  - BREAK-EVEN: only the stake-return leg posts, house untouched;
  - ZERO price (total loss): no wallet-credit leg, full stake swept to revenue;
  - rejections (no money moves): not owner, already settled, market closed, re-close;
  - race safety: a CLOSED bet is excluded from a later settlement pass.
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
    BET_CLOSED,
    BET_PENDING,
    BET_SETTLED_LOST,
    BET_SETTLED_WON,
    KIND_MARKET_LIABILITY,
)
from app.bets.exceptions import BetNotClosable, BetNotFound, MarketClosed
from app.bets.market_port import MARKET_CLOSED, MARKET_OPEN, MarketView, OutcomeView
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
from app.wallet.service import WalletService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine:
    """Depend on ``engine`` (container, migrate, env rewrite) — mirrors test_resolve_market.py."""
    return engine


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _bets_table(engine: AsyncEngine):
    """Create the ``bets`` table (DDL ships in migration 0005; created here for tests)."""
    async with engine.begin() as conn:
        await conn.run_sync(Bet.__table__.create, checkfirst=True)
    yield


# --------------------------------------------------------------------------- #
# Stub market source (for placement + re-pricing) + fake resolver + builders.
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
    """In-memory ``MarketResolvePort`` — records resolutions + reopenings (no markets table)."""

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


def _market(
    market_id: UUID,
    yes_id: UUID,
    no_id: UUID,
    *,
    yes_price: str,
    status: str = MARKET_OPEN,
    deadline: datetime | None = None,
) -> MarketView:
    """Build a market with FIXED outcome ids so the same outcome can be RE-PRICED after place."""
    return MarketView(
        id=market_id,
        status=status,
        deadline=deadline or (datetime.now(UTC) + timedelta(days=1)),
        outcomes=(
            OutcomeView(id=yes_id, label="YES", price=Decimal(yes_price)),
            OutcomeView(id=no_id, label="NO", price=Decimal("0.5")),
        ),
    )


# --------------------------------------------------------------------------- #
# Committed-session helpers (assert against committed state).
# --------------------------------------------------------------------------- #
async def _seed_wallet(balance: Decimal) -> tuple[UUID, UUID]:
    """Create a LEDGER-BACKED user_wallet at ``balance`` (committed); return (user_id, wallet_id).

    INSERTs at balance 0, then funds via the real ``WalletService.recharge`` (``house_promo ->
    wallet``, a proper ledger entry). A bare-balance INSERT leaves an orphan balance with no
    offsetting entry; because the testcontainer is session-scoped, the committed orphan leaks
    into other suites' DB-wide ledger-integrity gate (e.g. ``tests/settlement/test_event_*``),
    failing them depending on file ordering. The house singletons are snapshotted AFTER seeding
    in each test, so the funding recharge falls outside the before/after deltas.
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


async def _bet_by_id(bet_id: UUID) -> Bet:
    sm = _get_session_maker()
    async with sm() as s:
        return (await s.execute(select(Bet).where(Bet.id == bet_id))).scalar_one()


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


async def _sell(bet_id: UUID, user_id: UUID, src) -> dict:
    sm = _get_session_maker()
    async with sm() as s:
        return await BetService.sell_position(s, bet_id=bet_id, user_id=user_id, market_source=src)


# --------------------------------------------------------------------------- #
# 1) GAIN — payout above stake: stake back from liability + winnings from house_promo.
# --------------------------------------------------------------------------- #
async def test_sell_position_gain_pays_stake_plus_winnings() -> None:
    market_id, yes_id, no_id = uuid4(), uuid4(), uuid4()
    src = StubMarketSource()
    src.add(_market(market_id, yes_id, no_id, yes_price="0.5"))
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    m = src._markets[market_id]
    await _place(user_id, m, yes_id, Decimal("40.0000"), src)

    # Re-price YES up to 0.8 -> cashout = 40 * 0.8 / 0.5 = 64 (a 24 gain).
    src.add(_market(market_id, yes_id, no_id, yes_price="0.8"))
    promo_before = await _balance(HOUSE_PROMO_ACCOUNT_ID)
    revenue_before = await _balance(HOUSE_REVENUE_ACCOUNT_ID)

    bet_id = (await _bets_for_user(user_id))[0].id
    result = await _sell(bet_id, user_id, src)

    assert result["payout"] == Decimal("64.0000")
    assert result["pnl"] == Decimal("24.0000")
    assert result["exit_odds"] == Decimal("0.8")
    assert result["new_balance"] == Decimal("124.0000")  # 100 - 40 + 64

    assert await _balance(wallet_id) == Decimal("124.0000")
    assert await _balance(await _liability_id(market_id)) == Decimal("0.0000")
    # house_promo funded the 24 gain; house_revenue untouched.
    assert promo_before - await _balance(HOUSE_PROMO_ACCOUNT_ID) == Decimal("24.0000")
    assert await _balance(HOUSE_REVENUE_ACCOUNT_ID) == revenue_before

    bet = await _bet_by_id(bet_id)
    assert bet.status == BET_CLOSED
    assert bet.exit_odds == Decimal("0.800000")
    assert bet.closed_at is not None


# --------------------------------------------------------------------------- #
# 2) LOSS — payout below stake: cash-out from liability + shortfall to house_revenue.
# --------------------------------------------------------------------------- #
async def test_sell_position_loss_sweeps_shortfall_to_revenue() -> None:
    market_id, yes_id, no_id = uuid4(), uuid4(), uuid4()
    src = StubMarketSource()
    src.add(_market(market_id, yes_id, no_id, yes_price="0.5"))
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    m = src._markets[market_id]
    await _place(user_id, m, yes_id, Decimal("40.0000"), src)

    # Re-price YES down to 0.25 -> cashout = 40 * 0.25 / 0.5 = 20 (a 20 loss).
    src.add(_market(market_id, yes_id, no_id, yes_price="0.25"))
    promo_before = await _balance(HOUSE_PROMO_ACCOUNT_ID)
    revenue_before = await _balance(HOUSE_REVENUE_ACCOUNT_ID)

    bet_id = (await _bets_for_user(user_id))[0].id
    result = await _sell(bet_id, user_id, src)

    assert result["payout"] == Decimal("20.0000")
    assert result["pnl"] == Decimal("-20.0000")
    assert result["new_balance"] == Decimal("80.0000")  # 100 - 40 + 20

    assert await _balance(wallet_id) == Decimal("80.0000")
    assert await _balance(await _liability_id(market_id)) == Decimal("0.0000")
    # house_revenue gained the 20 shortfall; house_promo untouched.
    assert await _balance(HOUSE_REVENUE_ACCOUNT_ID) - revenue_before == Decimal("20.0000")
    assert await _balance(HOUSE_PROMO_ACCOUNT_ID) == promo_before

    assert (await _bet_by_id(bet_id)).status == BET_CLOSED


# --------------------------------------------------------------------------- #
# 3) BREAK-EVEN — price unchanged: only the stake-return leg posts, house untouched.
# --------------------------------------------------------------------------- #
async def test_sell_position_break_even_only_returns_stake() -> None:
    market_id, yes_id, no_id = uuid4(), uuid4(), uuid4()
    src = StubMarketSource()
    src.add(_market(market_id, yes_id, no_id, yes_price="0.5"))
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    m = src._markets[market_id]
    await _place(user_id, m, yes_id, Decimal("40.0000"), src)

    # YES stays at 0.5 -> cashout = 40 * 0.5 / 0.5 = 40 (break-even).
    promo_before = await _balance(HOUSE_PROMO_ACCOUNT_ID)
    revenue_before = await _balance(HOUSE_REVENUE_ACCOUNT_ID)

    bet_id = (await _bets_for_user(user_id))[0].id
    result = await _sell(bet_id, user_id, src)

    assert result["payout"] == Decimal("40.0000")
    assert result["pnl"] == Decimal("0.0000")
    assert result["new_balance"] == Decimal("100.0000")  # 100 - 40 + 40

    assert await _balance(wallet_id) == Decimal("100.0000")
    assert await _balance(await _liability_id(market_id)) == Decimal("0.0000")
    # Only the stake-return leg posts — neither house account moves.
    assert await _balance(HOUSE_PROMO_ACCOUNT_ID) == promo_before
    assert await _balance(HOUSE_REVENUE_ACCOUNT_ID) == revenue_before

    assert (await _bet_by_id(bet_id)).status == BET_CLOSED


# --------------------------------------------------------------------------- #
# 4) ZERO price (total loss) — no wallet-credit leg, full stake swept to revenue.
# --------------------------------------------------------------------------- #
async def test_sell_position_zero_price_total_loss() -> None:
    market_id, yes_id, no_id = uuid4(), uuid4(), uuid4()
    src = StubMarketSource()
    src.add(_market(market_id, yes_id, no_id, yes_price="0.5"))
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    m = src._markets[market_id]
    await _place(user_id, m, yes_id, Decimal("40.0000"), src)

    # Re-price YES to 0.0 -> cashout = 0 (total loss); the stake-return leg is skipped.
    src.add(_market(market_id, yes_id, no_id, yes_price="0.0"))
    promo_before = await _balance(HOUSE_PROMO_ACCOUNT_ID)
    revenue_before = await _balance(HOUSE_REVENUE_ACCOUNT_ID)

    bet_id = (await _bets_for_user(user_id))[0].id
    result = await _sell(bet_id, user_id, src)

    assert result["payout"] == Decimal("0.0000")
    assert result["pnl"] == Decimal("-40.0000")
    assert result["new_balance"] == Decimal("60.0000")  # 100 - 40 + 0

    assert await _balance(wallet_id) == Decimal("60.0000")
    assert await _balance(await _liability_id(market_id)) == Decimal("0.0000")
    # Whole stake swept to house_revenue; house_promo untouched.
    assert await _balance(HOUSE_REVENUE_ACCOUNT_ID) - revenue_before == Decimal("40.0000")
    assert await _balance(HOUSE_PROMO_ACCOUNT_ID) == promo_before

    bet = await _bet_by_id(bet_id)
    assert bet.status == BET_CLOSED
    assert bet.exit_odds == Decimal("0.000000")


# --------------------------------------------------------------------------- #
# 5) Not owner — BetNotFound; nothing moves, the bet stays PENDING.
# --------------------------------------------------------------------------- #
async def test_sell_position_rejected_when_not_owner() -> None:
    market_id, yes_id, no_id = uuid4(), uuid4(), uuid4()
    src = StubMarketSource()
    src.add(_market(market_id, yes_id, no_id, yes_price="0.5"))
    alice, alice_w = await _seed_wallet(Decimal("100.0000"))
    m = src._markets[market_id]
    await _place(alice, m, yes_id, Decimal("40.0000"), src)

    bet_id = (await _bets_for_user(alice))[0].id
    with pytest.raises(BetNotFound):
        await _sell(bet_id, uuid4(), src)  # a different player

    assert await _balance(alice_w) == Decimal("60.0000")  # 100 - 40 stake, unchanged
    assert (await _bet_by_id(bet_id)).status == BET_PENDING


# --------------------------------------------------------------------------- #
# 6) Already settled — BetNotClosable; the settled wallet value is unchanged.
# --------------------------------------------------------------------------- #
async def test_sell_position_rejected_when_already_settled() -> None:
    market_id, yes_id, no_id = uuid4(), uuid4(), uuid4()
    src = StubMarketSource()
    src.add(_market(market_id, yes_id, no_id, yes_price="0.5"))
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    m = src._markets[market_id]
    await _place(user_id, m, yes_id, Decimal("40.0000"), src)

    # Resolve YES so the bet becomes SETTLED_WON (payout 40 / 0.5 = 80 -> wallet 140).
    resolver = FakeMarketResolver()
    sm = _get_session_maker()
    async with sm() as session:
        await SettlementService.resolve_market(
            session,
            market_id=market_id,
            winning_outcome_id=yes_id,
            market_resolver=resolver,
            justification="resolved for test",
        )
    settled_balance = await _balance(wallet_id)
    assert settled_balance == Decimal("140.0000")

    bet_id = (await _bets_for_user(user_id))[0].id
    assert (await _bet_by_id(bet_id)).status == BET_SETTLED_WON
    with pytest.raises(BetNotClosable):
        await _sell(bet_id, user_id, src)

    assert await _balance(wallet_id) == settled_balance  # no change from the settled value


# --------------------------------------------------------------------------- #
# 7) Market closed — MarketClosed; nothing moves, bet PENDING, liability holds the stake.
# --------------------------------------------------------------------------- #
async def test_sell_position_rejected_when_market_closed() -> None:
    market_id, yes_id, no_id = uuid4(), uuid4(), uuid4()
    src = StubMarketSource()
    src.add(_market(market_id, yes_id, no_id, yes_price="0.5"))  # OPEN at placement
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    m = src._markets[market_id]
    await _place(user_id, m, yes_id, Decimal("40.0000"), src)

    # Re-add the market as CLOSED.
    src.add(_market(market_id, yes_id, no_id, yes_price="0.5", status=MARKET_CLOSED))

    bet_id = (await _bets_for_user(user_id))[0].id
    with pytest.raises(MarketClosed):
        await _sell(bet_id, user_id, src)

    assert await _balance(wallet_id) == Decimal("60.0000")  # 100 - 40 stake, unchanged
    assert (await _bet_by_id(bet_id)).status == BET_PENDING
    assert await _balance(await _liability_id(market_id)) == Decimal("40.0000")  # stake still held


# --------------------------------------------------------------------------- #
# 8) Re-close — second close is BetNotClosable; no double credit.
# --------------------------------------------------------------------------- #
async def test_sell_position_re_close_is_rejected() -> None:
    market_id, yes_id, no_id = uuid4(), uuid4(), uuid4()
    src = StubMarketSource()
    src.add(_market(market_id, yes_id, no_id, yes_price="0.5"))
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    m = src._markets[market_id]
    await _place(user_id, m, yes_id, Decimal("40.0000"), src)

    bet_id = (await _bets_for_user(user_id))[0].id
    await _sell(bet_id, user_id, src)  # first close succeeds (break-even -> wallet 100)
    after_first = await _balance(wallet_id)
    assert after_first == Decimal("100.0000")
    assert (await _bet_by_id(bet_id)).status == BET_CLOSED

    with pytest.raises(BetNotClosable):
        await _sell(bet_id, user_id, src)  # second close rejected

    assert await _balance(wallet_id) == after_first  # no double credit


# --------------------------------------------------------------------------- #
# 9) Race safety (sequential) — a CLOSED bet is excluded from a later settlement pass.
# --------------------------------------------------------------------------- #
async def test_closed_bet_excluded_from_later_settlement() -> None:
    market_id, yes_id, no_id = uuid4(), uuid4(), uuid4()
    src = StubMarketSource()
    src.add(_market(market_id, yes_id, no_id, yes_price="0.5"))
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    m = src._markets[market_id]
    await _place(user_id, m, yes_id, Decimal("40.0000"), src)

    bet_id = (await _bets_for_user(user_id))[0].id
    await _sell(bet_id, user_id, src)  # close at unchanged price -> payout 40, wallet 100
    after_close = await _balance(wallet_id)
    assert after_close == Decimal("100.0000")
    assert (await _bet_by_id(bet_id)).status == BET_CLOSED

    # Now resolve the market on YES — the CLOSED bet must NOT be re-settled.
    resolver = FakeMarketResolver()
    sm = _get_session_maker()
    async with sm() as session:
        plan = await SettlementService.resolve_market(
            session,
            market_id=market_id,
            winning_outcome_id=yes_id,
            market_resolver=resolver,
            justification="resolved for test",
        )

    assert plan.settled == ()  # the CLOSED bet is invisible to settlement
    assert await _balance(wallet_id) == after_close  # unchanged from the post-close snapshot
    assert (await _bet_by_id(bet_id)).status == BET_CLOSED


# Keep BET_SETTLED_LOST imported (parity with the settlement test module's symbol set).
_ = BET_SETTLED_LOST
