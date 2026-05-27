"""SettlementService — the transactional settlement pass (Phase 5, SC#5/#6).

Applies the pure :func:`~app.settlement.plan.build_settlement_plan` to the double-entry
ledger in ONE ACID transaction (all-or-nothing), then marks the market RESOLVED through the
:class:`~app.settlement.market_port.MarketResolvePort` on the SAME session. Built once here
and reused UNCHANGED by Phase 7's Polymarket auto-resolution (the architectural payoff of the
``MarketSource`` abstraction — the pure plan takes ``price`` as input, so it has zero Phase 4
coupling).

Ledger flows (v1 "odds locked at placement", no house edge — ARCHITECTURE.md): the per-market
liability account holds the sum of all stakes. For each settled bet:

  - WINNER: ``market_liability -> user_wallet`` for the bet's own ``stake`` (returned from the
    pool) PLUS ``house_promo -> user_wallet`` for the winnings ``payout - stake`` (the
    fixed-odds shortfall the house funds). The winnings leg is skipped when ``price == 1.0``
    (payout == stake, winnings 0) so no zero-amount entry hits ``CHECK (amount > 0)``.
  - LOSER:  ``market_liability -> house_revenue`` for the bet's ``stake``.

Across all bets the liability nets to zero (every stake leaves it). Reuses the VALIDATED Phase 3
``WalletService._post_transfer`` (the sole double-entry writer, WAL-07) with the FOR-UPDATE locks
acquired here in canonical UUID order (Spike 004 / Pitfall 3) before any posting.

Idempotency (SC#6): only ``PENDING`` bets are settled and each is flipped to
``SETTLED_WON`` / ``SETTLED_LOST``, so re-resolving a market settles nothing (a true no-op — no
double-credit). Each settlement transfer also carries a deterministic
``settle:{bet_id}:{leg}`` idempotency key, so a concurrent double-resolve collides on ``23505``
and rolls back instead of double-paying.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from app.bets.constants import BET_PENDING, KIND_MARKET_LIABILITY
from app.bets.models import Bet
from app.core.audit.service import AuditService
from app.settlement.constants import (
    SETTLE_LEG_LOSS,
    SETTLE_LEG_STAKE,
    SETTLE_LEG_WIN,
    TRANSFER_SETTLE_LOSS,
    TRANSFER_SETTLE_STAKE_RETURN,
    TRANSFER_SETTLE_WINNINGS,
    settle_idempotency_key,
)
from app.settlement.plan import BetToSettle, SettlementPlan, build_settlement_plan
from app.wallet.constants import (
    HOUSE_PROMO_ACCOUNT_ID,
    HOUSE_REVENUE_ACCOUNT_ID,
    OWNER_MARKET,
    PLAY_USD,
)
from app.wallet.models import Account
from app.wallet.service import WalletService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.settlement.market_port import MarketResolvePort

# One ledger transfer the settlement pass will post:
# (transfer_kind, leg_suffix, bet_id, debit_account_id, credit_account_id, amount).
_TransferSpec = tuple[str, str, UUID, UUID, UUID, Decimal]


class SettlementService:
    """The single entry point for resolving a market and settling its bets (Phase 5)."""

    @classmethod
    async def resolve_market(
        cls,
        session: AsyncSession,
        *,
        market_id: UUID,
        winning_outcome_id: UUID,
        market_resolver: MarketResolvePort,
        justification: str,
        actor_user_id: UUID | None = None,
    ) -> SettlementPlan:
        """Resolve ``market_id`` on ``winning_outcome_id`` and settle its pending bets (SC#5).

        Returns the :class:`SettlementPlan` describing what was paid. Idempotent (SC#6):
        a second call settles nothing because the bets are no longer ``PENDING``. The whole
        operation is one ACID transaction — the payouts, the market-status flip, AND the
        immutable audit row all commit together (a mid-way failure leaves NO payout, the bets
        ``PENDING``, the market unresolved, and no audit row).

        ``justification`` is the mandatory resolution reason (SC#5 two-step confirm); it is
        recorded in the ``settlement.resolved`` audit entry. ``actor_user_id`` is the resolving
        admin (``None`` => a system resolution, e.g. Phase 7 auto-resolution).

        ``winning_outcome_id`` is trusted to be a valid outcome of the market (the admin
        resolve endpoint validates it against Phase 4 at integration); the pure plan simply
        classifies each bet by ``outcome_id == winning_outcome_id``.
        """
        async with session.begin():
            # 1. Load the still-PENDING bets (the status filter is the primary idempotency
            #    guard — already-settled bets are invisible to a re-resolve, SC#6).
            bets = list(
                (
                    await session.execute(
                        select(Bet).where(
                            Bet.market_id == market_id,
                            Bet.status == BET_PENDING,
                        )
                    )
                )
                .scalars()
                .all()
            )

            # 2. Pure plan: classify won/lost + compute payouts from the price locked at
            #    placement (zero Phase 4 coupling — price is an input).
            plan = build_settlement_plan(
                [
                    BetToSettle(
                        bet_id=b.id,
                        outcome_id=b.outcome_id,
                        stake=b.stake,
                        price=b.odds_at_placement,
                    )
                    for b in bets
                ],
                winning_outcome_id=winning_outcome_id,
            )

            if bets:
                bet_by_id = {b.id: b for b in bets}
                liability_id = await cls._resolve_market_liability_id(session, market_id=market_id)

                # Resolve each distinct winner's wallet once.
                winner_wallets: dict[UUID, UUID] = {}
                for sb in plan.settled:
                    if sb.won:
                        uid = bet_by_id[sb.bet_id].user_id
                        if uid not in winner_wallets:
                            winner_wallets[uid] = await WalletService._resolve_user_wallet_id(
                                session, user_id=uid
                            )

                # 3. Derive the exact ledger transfers from the plan + flip each bet's status.
                specs: list[_TransferSpec] = []
                for sb in plan.settled:
                    bet = bet_by_id[sb.bet_id]
                    if sb.won:
                        wallet_id = winner_wallets[bet.user_id]
                        specs.append(
                            (
                                TRANSFER_SETTLE_STAKE_RETURN,
                                SETTLE_LEG_STAKE,
                                bet.id,
                                liability_id,
                                wallet_id,
                                bet.stake,
                            )
                        )
                        # sb.pnl == payout - stake (the winnings); zero only when price == 1.0.
                        if sb.pnl > 0:
                            specs.append(
                                (
                                    TRANSFER_SETTLE_WINNINGS,
                                    SETTLE_LEG_WIN,
                                    bet.id,
                                    HOUSE_PROMO_ACCOUNT_ID,
                                    wallet_id,
                                    sb.pnl,
                                )
                            )
                    else:
                        specs.append(
                            (
                                TRANSFER_SETTLE_LOSS,
                                SETTLE_LEG_LOSS,
                                bet.id,
                                liability_id,
                                HOUSE_REVENUE_ACCOUNT_ID,
                                bet.stake,
                            )
                        )
                    bet.status = sb.status

                # 4. Acquire every FOR UPDATE lock in canonical UUID order BEFORE posting any
                #    transfer (Spike 004 / Pitfall 3) so no lock-ordering cycle can form.
                touched = {s[3] for s in specs} | {s[4] for s in specs}
                for account_id in sorted(touched, key=str):
                    await session.execute(
                        select(Account.id).where(Account.id == account_id).with_for_update()
                    )

                # 5. Post the double-entry moves via the validated writer (locks held).
                for kind, leg, bet_id, debit_id, credit_id, amount in specs:
                    await WalletService._post_transfer(
                        session,
                        kind=kind,
                        idempotency_key=settle_idempotency_key(bet_id, leg),
                        actor_user_id=actor_user_id,
                        debit_account_id=debit_id,
                        credit_account_id=credit_id,
                        amount=amount,
                        metadata={"bet_id": str(bet_id), "market_id": str(market_id)},
                    )

            # 6. Mark the market RESOLVED on THIS session so the status flip is atomic with
            #    the payouts (a fake records it during parallel dev; Phase 4's service writes
            #    the markets row at integration).
            await market_resolver.mark_resolved(
                session, market_id=market_id, winning_outcome_id=winning_outcome_id
            )

            # 7. One immutable audit row, on THIS session so it commits atomically with the
            #    payouts (SC#5). The row's own occurred_at is the settlement_timestamp; money
            #    is recorded as a string, never a JSON float.
            await AuditService.record(
                session,
                actor=f"user:{actor_user_id}" if actor_user_id is not None else "system",
                event_type="settlement.resolved",
                payload={
                    "market_id": str(market_id),
                    "winning_outcome": str(winning_outcome_id),
                    "resolver": str(actor_user_id) if actor_user_id is not None else "system",
                    "justification": justification,
                    "total_payout": str(plan.total_payout),
                    "total_loser_stake": str(plan.total_loser_stake),
                    "bets_settled": len(plan.settled),
                },
            )

            return plan

    @staticmethod
    async def _resolve_market_liability_id(session: AsyncSession, *, market_id: UUID) -> UUID:
        """Return the per-market liability account id (read-only).

        It always exists once any bet has been placed (``BetService.place_bet`` creates it),
        so this is reached only when there are bets to settle.
        """
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
