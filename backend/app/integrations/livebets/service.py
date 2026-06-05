"""LiveBetsBridge — the verified, idempotent live-bets ledger mirror (v1.3, LB-A).

Mirrors a live-bets bet into XPredict's own double-entry ledger, reusing the
VALIDATED ``WalletService._post_transfer`` (the sole double-entry writer, WAL-07)
exactly as ``BetService.place_bet`` and ``SettlementService.resolve_market`` do:
the bridge OWNS its transaction (``session.begin()``), locks every touched account
in CANONICAL UUID ORDER (``sorted(..., key=str)``) before posting, and posts each
leg through the one writer. Zero behavior change to existing wallet/bets/settlement
tables — this module is purely additive.

Server-side verification (SC#5): every operation reads the authoritative status /
stake / payout from live-bets ``GET /v2/bets/{id}`` BEFORE posting — it NEVER trusts
a client-supplied amount. A status/stake mismatch raises (``LiveBetsVerificationError``)
without posting.

Idempotency (SC#4) is two-layer, mirroring settlement's design:
  - PRIMARY guard — the ``livebets_bets`` mirror row. ``record_placed`` upserts it
    with ``ON CONFLICT DO NOTHING``; a conflict means "already mirrored" -> no-op.
    ``record_settled`` reads the row and a ``status != PENDING`` means "already
    settled" -> no-op (the analogue of settlement's ``status = PENDING`` filter).
  - SECONDARY guard — the UNIQUE ``transfers.idempotency_key``. ``_post_transfer``
    does NOT itself catch ``23505`` (only ``recharge`` / ``transfer`` /
    ``grant_signup_bonus`` do), so the bridge catches ``IntegrityError`` with
    sqlstate ``23505`` and returns an idempotent no-op; any other IntegrityError
    re-raises.

LEDGER FLOWS (LOCKED — mirror ``app/settlement``):
  - placed:           ``user_wallet -> livebets_escrow`` (stake)
  - WON:              ``livebets_escrow -> user_wallet`` (stake)
                  + ``house_promo -> user_wallet`` (payout - stake), skipped when <= 0
  - LOST:             ``livebets_escrow -> house_revenue`` (stake)  [loss sink = house_revenue]
  - REFUNDED/VOIDED:  ``livebets_escrow -> user_wallet`` (stake)

ESCROW NETS TO ZERO: placed credits escrow +stake; WON debits escrow -stake (the
winnings come from ``house_promo``, not escrow); LOST debits escrow -stake (to
``house_revenue``); REFUNDED/VOIDED debit escrow -stake (to the wallet). So escrow
returns to its prior balance across any full placed -> settled cycle — exactly the
per-market-liability "nets to zero" property of ``app/settlement``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from app.integrations.livebets.constants import (
    LIVEBETS_ESCROW_ACCOUNT_ID,
    LIVEBETS_PENDING,
    LIVEBETS_REFUND_STATUSES,
    LIVEBETS_SETTLED_STATUSES,
    LIVEBETS_WON,
    TRANSFER_LIVEBETS_PLACED,
    TRANSFER_LIVEBETS_SETTLE_LOSS,
    TRANSFER_LIVEBETS_SETTLE_STAKE_RETURN,
    TRANSFER_LIVEBETS_SETTLE_WINNINGS,
    TRANSFER_LIVEBETS_VOID_REFUND,
    placed_idempotency_key,
    settled_idempotency_key,
    settled_stake_idempotency_key,
    settled_winnings_idempotency_key,
)
from app.integrations.livebets.models import LiveBetsBet
from app.integrations.livebets.schemas import MirrorResult, parse_verified_bet
from app.wallet.constants import HOUSE_PROMO_ACCOUNT_ID, HOUSE_REVENUE_ACCOUNT_ID
from app.wallet.models import Account
from app.wallet.service import WalletService

if TYPE_CHECKING:
    from decimal import Decimal

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.auth.models import User

# Postgres SQLSTATE for a unique-constraint violation — the idempotency signal
# on ``transfers.idempotency_key`` (mirrors WalletService.SQLSTATE_UNIQUE_VIOLATION).
SQLSTATE_UNIQUE_VIOLATION = "23505"


class LiveBetsVerificationError(Exception):
    """The live-bets verification (status/stake/payout) rejects the operation.

    Raised — WITHOUT posting any ledger move — when the bet read from
    ``GET /v2/bets/{id}`` is not in the expected state (e.g. ``record_placed`` for a
    non-PENDING bet, ``record_settled`` for a still-PENDING bet, a WON bet missing a
    payout, or a settle with no prior placed mirror row). The router maps it to a 4xx.
    """


class LiveBetsBetReader(Protocol):
    """The slice of ``LiveBetsClient`` the bridge needs — injected so tests fake it."""

    async def get_bet(self, bet_id: str) -> dict[str, object]: ...


# One ledger transfer the settle pass will post:
# (transfer_kind, idempotency_key, debit_account_id, credit_account_id, amount).
_TransferSpec = tuple[str, str, UUID, UUID, "Decimal"]


class LiveBetsBridge:
    """Verified, idempotent mirror of live-bets bets into the XPredict ledger."""

    @classmethod
    async def record_placed(
        cls,
        session: AsyncSession,
        *,
        user: User,
        bet_id: UUID,
        client: LiveBetsBetReader,
    ) -> MirrorResult:
        """Mirror a placed live-bets bet: debit ``user_wallet -> livebets_escrow`` (stake).

        Verifies the bet against live-bets FIRST (status must be PENDING; the
        authoritative stake is read from the response, never from the client), then
        in one owned transaction upserts the mirror row and posts the debit. Idempotent:
        a replay (mirror row already present, or duplicate idempotency key) is a no-op
        (``applied=False``) — no double-debit.
        """
        # 1. VERIFY FIRST (read-only, BEFORE session.begin() — mirrors place_bet
        #    validating the market before its tx).
        verified = parse_verified_bet(await client.get_bet(str(bet_id)))
        if verified.status != LIVEBETS_PENDING:
            raise LiveBetsVerificationError(
                f"live-bets bet {bet_id} is {verified.status}, expected PENDING for placed"
            )
        stake = verified.stake  # authoritative — never a client-supplied amount

        try:
            async with session.begin():
                wallet_id = await WalletService._resolve_user_wallet_id(
                    session, user_id=user.id
                )

                # 2. Upsert the mirror row — PRIMARY idempotency guard. A conflict on
                #    the bet_id PK means this bet was already mirrored: a replay, so we
                #    skip the transfer entirely (no double-debit). Mirrors the spirit of
                #    _ensure_market_liability_account's pg_insert/on_conflict, but here a
                #    conflict means "already mirrored", not "reuse infra".
                insert_result = await session.execute(
                    pg_insert(LiveBetsBet)
                    .values(
                        bet_id=bet_id,
                        user_id=user.id,
                        table_id=verified.table_id,
                        market_id=verified.market_id,
                        stake=stake,
                        status=LIVEBETS_PENDING,
                    )
                    .on_conflict_do_nothing(index_elements=["bet_id"])
                    .returning(LiveBetsBet.bet_id)
                )
                if insert_result.scalar_one_or_none() is None:
                    # Row already existed — replay, no post.
                    return MirrorResult(
                        bet_id=str(bet_id), status=LIVEBETS_PENDING, applied=False
                    )

                # 3. Canonical UUID lock order (Spike 004 / Pitfall 3) on the two
                #    touched accounts BEFORE posting — copy the place_bet idiom.
                first_id, second_id = sorted(
                    (wallet_id, LIVEBETS_ESCROW_ACCOUNT_ID), key=str
                )
                await session.execute(
                    select(Account.id).where(Account.id == first_id).with_for_update()
                )
                await session.execute(
                    select(Account.id).where(Account.id == second_id).with_for_update()
                )

                # 4. Post the debit via the sole writer (locks held, inside this tx).
                await WalletService._post_transfer(
                    session,
                    kind=TRANSFER_LIVEBETS_PLACED,
                    idempotency_key=placed_idempotency_key(bet_id),
                    actor_user_id=user.id,
                    debit_account_id=wallet_id,
                    credit_account_id=LIVEBETS_ESCROW_ACCOUNT_ID,
                    amount=stake,
                    metadata={
                        "bet_id": str(bet_id),
                        "table_id": str(verified.table_id) if verified.table_id else None,
                    },
                )
        except IntegrityError as exc:
            # SECONDARY guard: the UNIQUE transfers.idempotency_key collided on a
            # concurrent double-placed (the mirror-row upsert raced). _post_transfer
            # does not catch 23505, so the bridge does. Any other IntegrityError re-raises.
            if getattr(exc.orig, "sqlstate", None) == SQLSTATE_UNIQUE_VIOLATION:
                return MirrorResult(
                    bet_id=str(bet_id), status=LIVEBETS_PENDING, applied=False
                )
            raise

        return MirrorResult(bet_id=str(bet_id), status=LIVEBETS_PENDING, applied=True)

    @classmethod
    async def record_settled(
        cls,
        session: AsyncSession,
        *,
        user: User,
        bet_id: UUID,
        client: LiveBetsBetReader,
    ) -> MirrorResult:
        """Mirror a settled live-bets bet (WON / LOST / REFUNDED / VOIDED).

        Verifies the terminal status against live-bets FIRST; for WON reads the
        authoritative payout (raises if absent). The stake is read from the mirror
        row captured at placement (server-side truth), never from the client. Idempotent:
        a replay (mirror row already non-PENDING) is a no-op (``applied=False``).

        Ledger by outcome (LOCKED): WON = escrow->wallet stake + house_promo->wallet
        winnings; LOST = escrow->house_revenue stake; REFUNDED/VOIDED = escrow->wallet
        stake.
        """
        # 1. VERIFY FIRST (read-only, non-DB, BEFORE session.begin()). The live-bets
        #    GET /v2/bets/{id} status check trusts no client amount and posts nothing —
        #    it correctly stays outside the owned tx (mirrors place_bet validating the
        #    market before its tx).
        verified = parse_verified_bet(await client.get_bet(str(bet_id)))
        if verified.status not in LIVEBETS_SETTLED_STATUSES:
            raise LiveBetsVerificationError(
                f"live-bets bet {bet_id} is {verified.status}, expected a settled status"
            )

        try:
            async with session.begin():
                # 2. Read the mirror row (the stake captured at placement — server-side
                #    truth) and apply the PRIMARY idempotency guard (status != PENDING =>
                #    replay) INSIDE the owned tx. Issuing these reads before
                #    ``session.begin()`` would autobegin an implicit tx and make
                #    ``begin()`` raise "a transaction is already begun" — exactly the
                #    ordering ``record_placed`` / ``recharge`` / ``resolve_market`` use
                #    (begin first, then read/resolve). The primary guard early-returns
                #    from inside the block, committing an empty tx (a clean no-op).
                mirror = (
                    await session.execute(
                        select(LiveBetsBet).where(LiveBetsBet.bet_id == bet_id)
                    )
                ).scalar_one_or_none()
                if mirror is None:
                    # The settle arrived before placed — the demo's placed event always
                    # precedes settled (webhook backstop is out of scope per CONTEXT).
                    raise LiveBetsVerificationError(
                        f"no placed mirror row for live-bets bet {bet_id} — settle before placed"
                    )
                if mirror.status != LIVEBETS_PENDING:
                    return MirrorResult(
                        bet_id=str(bet_id), status=mirror.status, applied=False
                    )

                stake = mirror.stake  # authoritative captured stake, never a client amount
                wallet_id = await WalletService._resolve_user_wallet_id(
                    session, user_id=user.id
                )

                # 3. Derive the leg specs by outcome (mirrors resolve_market's
                #    winner/loser legs).
                specs: list[_TransferSpec] = []
                if verified.status == LIVEBETS_WON:
                    if verified.payout is None:
                        raise LiveBetsVerificationError(
                            f"live-bets WON bet {bet_id} has no payout — cannot verify winnings"
                        )
                    specs.append(
                        (
                            TRANSFER_LIVEBETS_SETTLE_STAKE_RETURN,
                            settled_stake_idempotency_key(bet_id),
                            LIVEBETS_ESCROW_ACCOUNT_ID,
                            wallet_id,
                            stake,
                        )
                    )
                    winnings = verified.payout - stake
                    # Skip leg 2 when winnings <= 0 so no zero/negative amount hits
                    # CHECK (amount > 0) — mirrors settlement's `if sb.pnl > 0` guard.
                    if winnings > 0:
                        specs.append(
                            (
                                TRANSFER_LIVEBETS_SETTLE_WINNINGS,
                                settled_winnings_idempotency_key(bet_id),
                                HOUSE_PROMO_ACCOUNT_ID,
                                wallet_id,
                                winnings,
                            )
                        )
                elif verified.status in LIVEBETS_REFUND_STATUSES:
                    # REFUNDED or VOIDED — both take the single stake-return leg to the wallet.
                    specs.append(
                        (
                            TRANSFER_LIVEBETS_VOID_REFUND,
                            settled_idempotency_key(bet_id),
                            LIVEBETS_ESCROW_ACCOUNT_ID,
                            wallet_id,
                            stake,
                        )
                    )
                else:
                    # LOST — single leg, escrow -> house_revenue (loss sink, LOCKED decision).
                    specs.append(
                        (
                            TRANSFER_LIVEBETS_SETTLE_LOSS,
                            settled_idempotency_key(bet_id),
                            LIVEBETS_ESCROW_ACCOUNT_ID,
                            HOUSE_REVENUE_ACCOUNT_ID,
                            stake,
                        )
                    )

                # 4. Lock EVERY touched account in canonical UUID order BEFORE posting
                #    (copy the resolve_market `touched = {...}; for ... sorted(...)` idiom).
                touched = {s[2] for s in specs} | {s[3] for s in specs}
                for account_id in sorted(touched, key=str):
                    await session.execute(
                        select(Account.id).where(Account.id == account_id).with_for_update()
                    )

                # 5. Post each leg via the sole writer (per-leg key + metadata).
                for kind, key, debit_id, credit_id, amount in specs:
                    await WalletService._post_transfer(
                        session,
                        kind=kind,
                        idempotency_key=key,
                        actor_user_id=user.id,
                        debit_account_id=debit_id,
                        credit_account_id=credit_id,
                        amount=amount,
                        metadata={"bet_id": str(bet_id)},
                    )

                # 6. Flip the mirror row to the terminal status within this tx.
                await session.execute(
                    update(LiveBetsBet)
                    .where(LiveBetsBet.bet_id == bet_id)
                    .values(status=verified.status, settled_at=func.now())
                )
        except IntegrityError as exc:
            # SECONDARY guard: per-leg keys collide on a concurrent double-settle.
            if getattr(exc.orig, "sqlstate", None) == SQLSTATE_UNIQUE_VIOLATION:
                return MirrorResult(
                    bet_id=str(bet_id), status=verified.status, applied=False
                )
            raise

        return MirrorResult(bet_id=str(bet_id), status=verified.status, applied=True)
