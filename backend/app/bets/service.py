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

from app.bets.constants import (
    BET_CLOSED,
    BET_PENDING,
    CLOSE_LEG_LOSS,
    CLOSE_LEG_STAKE,
    CLOSE_LEG_WIN,
    KIND_MARKET_LIABILITY,
    TRANSFER_BET_PLACED,
    TRANSFER_CLOSE_LOSS,
    TRANSFER_CLOSE_STAKE_RETURN,
    TRANSFER_CLOSE_WINNINGS,
    close_idempotency_key,
)
from app.bets.exceptions import (
    BetNotClosable,
    BetNotFound,
    InvalidOutcome,
    MarketClosed,
    MarketNotFound,
    StakeOutOfRange,
)
from app.bets.models import Bet
from app.bets.portfolio import Portfolio, PositionInput, build_portfolio
from app.core.config import get_settings
from app.settlement.payout import cashout_value, profit_or_loss
from app.wallet.constants import (
    HOUSE_PROMO_ACCOUNT_ID,
    HOUSE_REVENUE_ACCOUNT_ID,
    OWNER_MARKET,
    PLAY_USD,
)
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
        on an ineligible market, :class:`StakeOutOfRange` when the stake falls outside the
        effective per-market (or global-fallback) limits,
        :class:`~app.wallet.exceptions.InsufficientBalance` if the wallet cannot cover the
        stake, and ``ValueError`` on a non-positive stake — in every rejection case NO money
        moves and NO bet is recorded.
        """
        if stake <= 0:
            raise ValueError("stake must be > 0")

        # Defensive: clear any transaction inherited from dependency resolution
        # before our own session.begin() calls below. get_user_db now uses a
        # DEDICATED session so the request session should arrive clean, but the
        # money path guards anyway — belt-and-suspenders, mirroring
        # app/settlement/router.py. A stray inherited read-tx would otherwise make
        # _ensure_market_liability_account's begin() raise "transaction already begun".
        if session.in_transaction():
            await session.rollback()

        # 1. Validate the market via the port (read-only; MUST NOT touch `session`).
        market = await market_source.get_market(market_id)
        if market is None:
            raise MarketNotFound(f"no market {market_id}")
        if not market.is_open(datetime.now(UTC)):
            raise MarketClosed(f"market {market_id} is not open for bets")
        chosen = market.outcome(outcome_id)
        if chosen is None:
            raise InvalidOutcome(f"outcome {outcome_id} not in market {market_id}")

        # 1b. Per-market stake limits (BET-06, server-authoritative) — checked with the
        # market in hand, BEFORE any DB work. Prefer the per-market bound; fall back to the
        # global config when the market column is NULL (no behavior change for existing
        # markets). The router maps StakeOutOfRange to HTTP 422; the client mirror is UX-only.
        settings = get_settings()
        min_stake = market.min_stake if market.min_stake is not None else settings.BET_MIN_STAKE
        max_stake = market.max_stake if market.max_stake is not None else settings.BET_MAX_STAKE
        if not (min_stake <= stake <= max_stake):
            raise StakeOutOfRange(f"Stake must be between {min_stake} and {max_stake}.")

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
    async def get_portfolio(
        cls, session: AsyncSession, *, user_id: UUID, market_source: MarketReadPort
    ) -> Portfolio:
        """Return ``user_id``'s portfolio — open + settled positions with P&L (SC#7, read-only).

        OPEN positions are marked to market against each outcome's LIVE ``current_odds`` (read
        through ``market_source``, the same port ``place_bet`` validates with): the unrealized
        P&L is ``current_value - stake`` where ``current_value = stake * current_odds /
        odds_at_placement``. When a market/outcome price is unavailable the position falls back
        to a neutral view (``current_value == stake``, ``unrealized_pnl == 0``). SETTLED
        positions carry the realized P&L exactly as settlement posted. No INSERT/UPDATE/commit.
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

        # Live current odds for OPEN positions — one read per distinct market (no N+1).
        open_market_ids = {b.market_id for b in bets if b.status == BET_PENDING}
        current_prices: dict[tuple[UUID, UUID], Decimal] = {}
        for market_id in open_market_ids:
            market = await market_source.get_market(market_id)
            if market is None:
                continue
            for outcome in market.outcomes:
                current_prices[(market_id, outcome.id)] = outcome.price

        return build_portfolio(
            [
                PositionInput(
                    bet_id=b.id,
                    market_id=b.market_id,
                    outcome_id=b.outcome_id,
                    stake=b.stake,
                    odds_at_placement=b.odds_at_placement,
                    status=b.status,
                    current_odds=current_prices.get((b.market_id, b.outcome_id)),
                    exit_odds=b.exit_odds,
                )
                for b in bets
            ]
        )

    @classmethod
    async def sell_position(
        cls,
        session: AsyncSession,
        *,
        bet_id: UUID,
        user_id: UUID,
        market_source: MarketReadPort,
    ) -> dict[str, UUID | Decimal]:
        """Close (cash out) ``user_id``'s open ``bet_id`` at the live price, in ONE ACID tx.

        The house is the counterparty (as at settlement): the player is paid the current
        mark-to-market value ``cashout_value(stake, odds_at_placement, current_odds)`` — fair
        value, no fee (v1, no house edge). The bet's stake leaves the per-market liability pool;
        a GAIN above stake is funded by ``house_promo``, a LOSS below stake is swept to
        ``house_revenue`` (so this bet's liability nets to zero, exactly like settlement). The
        bet flips ``PENDING -> CLOSED`` with ``closed_at`` / ``exit_odds`` recorded.

        Raises :class:`BetNotFound` (no such bet for this user), :class:`BetNotClosable` (not
        PENDING — already settled/closed), :class:`MarketNotFound` / :class:`MarketClosed`
        (market gone or not open), :class:`InvalidOutcome` (outcome missing). On every rejection
        NO money moves and the bet is unchanged. Returns
        ``{bet_id, payout, pnl, exit_odds, new_balance}``.
        """
        # Defensive: clear any inherited tx before our own session.begin() (mirrors place_bet).
        if session.in_transaction():
            await session.rollback()

        # 1. Load the bet (no lock yet) to discover market/outcome; validate ownership + status.
        bet = (await session.execute(select(Bet).where(Bet.id == bet_id))).scalar_one_or_none()
        if bet is None or bet.user_id != user_id:
            raise BetNotFound(f"no open bet {bet_id} for this player")
        if bet.status != BET_PENDING:
            raise BetNotClosable(f"bet {bet_id} cannot be closed (status {bet.status})")

        # The bet-load above AUTOBEGAN an implicit read tx on this session; end it (no locks
        # held, no writes) so the atomic ``session.begin()`` below opens the OUTERMOST tx
        # rather than raising "a transaction is already begun". The bet is the source of
        # truth only under the FOR UPDATE re-read inside that block.
        if session.in_transaction():
            await session.rollback()

        # 3. Atomic close: lock bet, re-verify, read market, compute payout, post ledger, flip status.
        async with session.begin():
            now = datetime.now(UTC)
            locked = (
                await session.execute(select(Bet).where(Bet.id == bet_id).with_for_update())
            ).scalar_one()
            # Re-check under the row lock — a concurrent close/resolve may have won the race.
            if locked.status != BET_PENDING:
                raise BetNotClosable(f"bet {bet_id} was already settled or closed")

            # Validate market and compute payout inside the lock — consistent with the locked bet data.
            market = await market_source.get_market(locked.market_id)
            if market is None:
                raise MarketNotFound(f"no market {locked.market_id}")
            if not market.is_open(now):
                raise MarketClosed(f"market {locked.market_id} is not open — cannot close")
            chosen = market.outcome(locked.outcome_id)
            if chosen is None:
                raise InvalidOutcome(f"outcome {locked.outcome_id} not in market {locked.market_id}")
            current_price = chosen.price
            payout = cashout_value(locked.stake, locked.odds_at_placement, current_price)
            pnl = profit_or_loss(locked.stake, payout)

            wallet_id = await WalletService._resolve_user_wallet_id(session, user_id=user_id)
            liability_id = await cls._resolve_market_liability_id(session, market_id=locked.market_id)

            stake = locked.stake
            # Close legs (mirror settlement). Skip any zero-amount leg (CHECK amount > 0).
            # (kind, leg, debit_account_id, credit_account_id, amount)
            specs: list[tuple[str, str, UUID, UUID, Decimal]] = []
            if payout >= stake:
                specs.append(
                    (TRANSFER_CLOSE_STAKE_RETURN, CLOSE_LEG_STAKE, liability_id, wallet_id, stake)
                )
                gain = payout - stake
                if gain > 0:
                    specs.append(
                        (
                            TRANSFER_CLOSE_WINNINGS,
                            CLOSE_LEG_WIN,
                            HOUSE_PROMO_ACCOUNT_ID,
                            wallet_id,
                            gain,
                        )
                    )
            else:
                if payout > 0:
                    specs.append(
                        (
                            TRANSFER_CLOSE_STAKE_RETURN,
                            CLOSE_LEG_STAKE,
                            liability_id,
                            wallet_id,
                            payout,
                        )
                    )
                specs.append(
                    (
                        TRANSFER_CLOSE_LOSS,
                        CLOSE_LEG_LOSS,
                        liability_id,
                        HOUSE_REVENUE_ACCOUNT_ID,
                        stake - payout,
                    )
                )

            # Lock every touched account FOR UPDATE in canonical UUID order (Spike 004 / Pitfall 3).
            touched = {s[2] for s in specs} | {s[3] for s in specs}
            for account_id in sorted(touched, key=str):
                await session.execute(
                    select(Account.id).where(Account.id == account_id).with_for_update()
                )

            # Post the double-entry moves via the validated writer (locks held).
            for kind, leg, debit_id, credit_id, amount in specs:
                await WalletService._post_transfer(
                    session,
                    kind=kind,
                    idempotency_key=close_idempotency_key(bet_id, leg),
                    actor_user_id=user_id,
                    debit_account_id=debit_id,
                    credit_account_id=credit_id,
                    amount=amount,
                    metadata={"bet_id": str(bet_id), "market_id": str(locked.market_id)},
                )

            locked.status = BET_CLOSED
            locked.closed_at = now
            locked.exit_odds = current_price

        # Post-commit wallet balance for the response.
        new_balance = (
            await session.execute(select(Account.balance).where(Account.id == wallet_id))
        ).scalar_one()
        return {
            "bet_id": bet_id,
            "payout": payout,
            "pnl": pnl,
            "exit_odds": current_price,
            "new_balance": new_balance,
        }

    @staticmethod
    async def _resolve_market_liability_id(session: AsyncSession, *, market_id: UUID) -> UUID:
        """Return the per-market liability account id (read-only). Exists once a bet was placed."""
        return (
            await session.execute(
                select(Account.id).where(
                    Account.owner_type == OWNER_MARKET,
                    Account.owner_id == market_id,
                    Account.kind == KIND_MARKET_LIABILITY,
                    Account.currency == PLAY_USD,
                )
            )
        ).scalar_one()

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
