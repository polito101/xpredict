"""BetService — atomic bet placement (Phase 5, SC#1).

``place_bet`` records a player's stake on a market outcome in ONE ACID transaction:
validate the market (via :class:`MarketReadPort`), lock the wallet + the per-market
liability account, check the balance, INSERT the bet, and post the double-entry ledger
move (debit ``user_wallet`` / credit ``market_liability``) — all-or-nothing (a
kill-mid-transaction failure leaves neither the bet nor any ledger entry).

Reuses the VALIDATED Phase 3 wallet primitives WITHOUT modifying them: the canonical
FOR-UPDATE lock order + ``WalletService._post_transfer`` (the sole double-entry writer,
WAL-07). This is the reuse the architecture intends ("Phase 5 bet-placement reuses
transfer"); ``place_bet`` owns the transaction so the bet INSERT and the ledger move
commit atomically — which ``WalletService.transfer`` (self-committing) cannot do.

The per-market liability account (``owner_type=market``, ``kind=market_liability``) is
created lazily + race-safely (``ON CONFLICT DO UPDATE … RETURNING``) in its OWN unit of
work BEFORE the bet transaction, so a concurrent first-bet cannot raise a 23505 that
would poison the bet tx, and an empty (balance-0) liability account left by a rolled-back
bet is harmless, reusable infrastructure.

Market validation flows through ``MarketReadPort``, NOT a DB FK — Phase 4 owns the
markets domain and the FK from ``bets`` is added by the integration migration ``0005``.
The port read MUST NOT use this service's ``session`` (the test stub does not; Phase 4's
adapter must read on its own path) so it cannot autobegin a tx before ``session.begin()``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.bets.constants import BET_PENDING, KIND_MARKET_LIABILITY, TRANSFER_BET_PLACED
from app.bets.exceptions import InvalidOutcome, MarketClosed, MarketNotFound
from app.bets.models import Bet
from app.bets.portfolio import Portfolio, PositionInput, build_portfolio
from app.wallet.constants import OWNER_MARKET, PLAY_USD
from app.wallet.exceptions import InsufficientBalance
from app.wallet.models import Account
from app.wallet.service import WalletService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.bets.market_port import MarketReadPort

# The accounts (owner_type, owner_id, kind, currency) unique key — for the race-safe
# liability upsert (defined in app/wallet/models.py Account.__table_args__).
_ACCOUNTS_OWNER_KIND_CURRENCY_KEY = "accounts_owner_kind_currency_key"


class BetService:
    """Bet placement (Phase 5). The single entry point for staking on a market."""

    @classmethod
    async def place_bet(
        cls,
        session: AsyncSession,
        *,
        user_id: UUID,
        market_id: UUID,
        outcome_id: UUID,
        stake: Decimal,
        market_source: MarketReadPort,
    ) -> Bet:
        """Place ``stake`` by ``user_id`` on ``outcome_id`` of ``market_id`` (SC#1).

        Raises :class:`MarketNotFound` / :class:`MarketClosed` / :class:`InvalidOutcome`
        on an ineligible market, :class:`~app.wallet.exceptions.InsufficientBalance` if
        the wallet cannot cover the stake, and ``ValueError`` on a non-positive stake —
        in every rejection case NO money moves and NO bet is recorded.
        """
        if stake <= 0:
            raise ValueError("stake must be > 0")

        # 1. Validate the market via the port (read-only; MUST NOT touch `session`).
        market = await market_source.get_market(market_id)
        if market is None:
            raise MarketNotFound(f"no market {market_id}")
        if not market.is_open(datetime.now(UTC)):
            raise MarketClosed(f"market {market_id} is not open for bets")
        chosen = market.outcome(outcome_id)
        if chosen is None:
            raise InvalidOutcome(f"outcome {outcome_id} not in market {market_id}")

        # 2. Ensure the per-market liability account exists (race-safe, own unit of work).
        liability_id = await cls._ensure_market_liability_account(session, market_id=market_id)

        # 3. Atomic bet placement (SC#1): lock -> check -> insert bet -> ledger -> commit.
        async with session.begin():
            wallet_id = await WalletService._resolve_user_wallet_id(session, user_id=user_id)

            # Canonical UUID lock order (Spike 004 / Pitfall 3) BEFORE mutating.
            first_id, second_id = sorted((wallet_id, liability_id), key=str)
            await session.execute(
                select(Account.id).where(Account.id == first_id).with_for_update()
            )
            await session.execute(
                select(Account.id).where(Account.id == second_id).with_for_update()
            )

            # Re-read the locked wallet balance; reject an overdraw with a domain error
            # (the lock guarantees no concurrent debit races between read and write).
            balance = (
                await session.execute(select(Account.balance).where(Account.id == wallet_id))
            ).scalar_one()
            if balance < stake:
                raise InsufficientBalance(f"wallet {wallet_id} balance {balance} < stake {stake}")

            bet = Bet(
                user_id=user_id,
                market_id=market_id,
                outcome_id=outcome_id,
                stake=stake,
                # Lock the chosen outcome's price (Phase 4 odds) at placement — settlement
                # pays a winner stake / odds_at_placement, so it must NOT be re-read later.
                odds_at_placement=chosen.price,
                status=BET_PENDING,
            )
            session.add(bet)
            await session.flush()  # populate bet.id for the transfer metadata

            # Reuse the VALIDATED double-entry writer (locks already held, inside this tx).
            await WalletService._post_transfer(
                session,
                kind=TRANSFER_BET_PLACED,
                idempotency_key=None,
                actor_user_id=user_id,
                debit_account_id=wallet_id,
                credit_account_id=liability_id,
                amount=stake,
                metadata={
                    "bet_id": str(bet.id),
                    "market_id": str(market_id),
                    "outcome_id": str(outcome_id),
                },
            )
            return bet

    @classmethod
    async def get_portfolio(cls, session: AsyncSession, *, user_id: UUID) -> Portfolio:
        """Return ``user_id``'s portfolio — open + settled positions with P&L (SC#7, read-only).

        Reads the player's bets (newest first) and runs the pure
        :func:`~app.bets.portfolio.build_portfolio`: OPEN positions carry the potential
        payout at the LOCKED odds, SETTLED positions carry the realized P&L. No
        INSERT/UPDATE/commit. Live unrealized P&L at CURRENT odds is enriched at integration
        once the market read port is wired (the locked-odds view here needs no Phase 4 data).
        """
        bets = list(
            (
                await session.execute(
                    select(Bet).where(Bet.user_id == user_id).order_by(Bet.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return build_portfolio(
            [
                PositionInput(
                    bet_id=b.id,
                    market_id=b.market_id,
                    outcome_id=b.outcome_id,
                    stake=b.stake,
                    odds_at_placement=b.odds_at_placement,
                    status=b.status,
                )
                for b in bets
            ]
        )

    @staticmethod
    async def _ensure_market_liability_account(session: AsyncSession, *, market_id: UUID) -> UUID:
        """Get-or-create the per-market liability account race-safely; return its id.

        ``ON CONFLICT DO UPDATE … RETURNING`` yields the row id whether this call
        inserts it or another concurrent first-bet already did — with no 23505 to poison
        the caller's transaction and no read-visibility gap. Runs in its OWN unit of work
        so the (idempotent, balance-0) account commits before the bet tx; an empty
        liability account left behind by a rolled-back bet is harmless.
        """
        async with session.begin():
            result = await session.execute(
                pg_insert(Account)
                .values(
                    owner_type=OWNER_MARKET,
                    owner_id=market_id,
                    kind=KIND_MARKET_LIABILITY,
                    currency=PLAY_USD,
                    balance=Decimal("0"),
                )
                .on_conflict_do_update(
                    constraint=_ACCOUNTS_OWNER_KIND_CURRENCY_KEY,
                    set_={"owner_id": market_id},  # no-op touch so RETURNING yields the row
                )
                .returning(Account.id)
            )
            return result.scalar_one()
