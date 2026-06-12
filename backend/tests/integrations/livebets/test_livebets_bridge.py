"""LiveBetsBridge — verified, idempotent live-bets ledger mirror (v1.3, LB-A, SC4/SC5/SC6).

Integration tests (testcontainers). Mirrors ``tests/settlement/test_resolve_market.py``
EXACTLY: the ``engine`` fixture runs ``alembic upgrade head`` (which, via migration
``0011_livebets_bridge``, creates the ``livebets_escrow`` singleton AND the
``livebets_bets`` mirror table in the container — so unlike ``bets`` we do NOT create
``livebets_bets`` via a ``Base.metadata`` fixture, it is a real migration table now).

The committed-session pattern (own ``_get_session_maker()`` sessions) is used because
``LiveBetsBridge`` owns its ``session.begin()`` unit of work, exactly like
``resolve_market``. Because the testcontainer is session-scoped, committed writes
persist across tests; the SHARED ``house_promo`` / ``house_revenue`` / ``livebets_escrow``
singletons therefore use BEFORE/AFTER deltas, while per-test wallets and per-test
``bet_id``s use fresh ``uuid4()`` and assert absolute values.

The ``FakeLiveBetsClient`` (no network) is the ONLY bet source — the suite is hermetic.

Covered:
  - placed->won: wallet down by stake then up by stake + winnings; escrow nets to 0;
    winnings funded by house_promo; mirror row WON with settled_at; bets table untouched.
  - placed->lost: wallet down by stake; escrow nets to 0; house_revenue gains the stake.
  - placed->REFUNDED and placed->VOIDED (the two REAL refund statuses — no ``VOID``):
    wallet whole again; escrow nets to 0; mirror row REFUNDED / VOIDED.
  - won with payout == stake: only the stake-return leg posts; house_promo untouched.
  - duplicate placed / duplicate settled: no second transfer, applied=False, balances
    unchanged (PRIMARY mirror-row guard).
  - SECONDARY 23505 guard on the two-leg WON path: a pre-inserted colliding per-leg key
    (mirror row still PENDING so the primary guard does NOT short-circuit) is caught,
    applied=False, no half-applied settle.
  - verification rejects mismatch: record_placed when status != PENDING, record_settled
    when still PENDING, WON with no payout -> LiveBetsVerificationError, zero ledger effect.
  - server-side stake authority: only the live-bets stake moves (the request carries only
    a bet_id), proven by seeding get_bet with a known stake and asserting exactly it moved.
"""

from __future__ import annotations

import types
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text

from app.db.session import _get_session_maker
from app.integrations.livebets.constants import (
    LIVEBETS_ESCROW_ACCOUNT_ID,
    LIVEBETS_LOST,
    LIVEBETS_PENDING,
    LIVEBETS_REFUNDED,
    LIVEBETS_VOIDED,
    LIVEBETS_WON,
    settled_stake_idempotency_key,
)
from app.integrations.livebets.models import LiveBetsBet
from app.integrations.livebets.service import LiveBetsBridge, LiveBetsVerificationError
from app.wallet.constants import (
    HOUSE_PROMO_ACCOUNT_ID,
    HOUSE_REVENUE_ACCOUNT_ID,
    KIND_USER_WALLET,
    OWNER_USER,
    PLAY_USD,
)
from app.wallet.models import Account, Transfer

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine:
    """Depend on ``engine`` (container, migrate, env rewrite) — mirrors test_resolve_market.py.

    The migration (0011) creates ``livebets_escrow`` + ``livebets_bets`` in the container,
    so there is deliberately NO ``Base.metadata`` table-create fixture here.
    """
    return engine


# --------------------------------------------------------------------------- #
# FakeLiveBetsClient — a tiny in-memory double of the LiveBetsClient surface the
# bridge calls (get_bet only). No network: the suite is hermetic.
# --------------------------------------------------------------------------- #
class FakeLiveBetsClient:
    """In-memory stand-in for ``LiveBetsClient`` — matches the bridge's reader slice."""

    def __init__(self) -> None:
        self._bets: dict[str, dict[str, object]] = {}

    def set_bet(
        self,
        bet_id: object,
        *,
        status: str,
        stake: Decimal,
        market_id: object | None = None,
        table_id: object | None = None,  # BetView has no table_id; kept for call-site parity
        payout: Decimal | None = None,
    ) -> None:
        # REAL live-bets BetView shape (live_bets/api/routes/bets.py): the id field
        # is `id` (NOT `bet_id`), the side is `selection` (NOT `side`), there is NO
        # `table_id`, and `payout` is str|None. We mirror those keys so the suite
        # actually proves the contract the client parses.
        self._bets[str(bet_id)] = {
            "id": str(bet_id),
            "round_id": str(bet_id),  # placeholder UUID — unused by the bridge
            "market_id": market_id,
            "selection": "over",
            "stake": stake,
            "locked_odds": "2.000",
            "status": status,
            "payout": payout,
            "placed_at": "2026-01-01T00:00:00Z",
            "settled_at": None,
        }

    async def get_bet(self, bet_id: str) -> dict[str, object]:
        return self._bets[str(bet_id)]

    async def mint_session(self, **kw: object) -> dict[str, object]:
        return {"session_token": "fake", "expires_at": "2026-01-01T00:00:00Z"}

    async def list_tables(self) -> dict[str, object]:
        # REAL GET /tables envelope: TableListResponse {tables: [...]}.
        return {"tables": []}


def _user(user_id: UUID) -> types.SimpleNamespace:
    """A minimal ``user`` stand-in — the bridge only reads ``user.id``
    (``WalletService._resolve_user_wallet_id(session, user_id=user.id)``)."""
    return types.SimpleNamespace(id=user_id)


# --------------------------------------------------------------------------- #
# Committed-session helpers (assert against committed state) — _seed_wallet and
# _balance copied verbatim from test_resolve_market.py.
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


async def _livebets_escrow_balance() -> Decimal:
    """The shared livebets_escrow singleton balance (asserted via BEFORE/AFTER deltas)."""
    return await _balance(LIVEBETS_ESCROW_ACCOUNT_ID)


async def _mirror_row(bet_id: UUID) -> LiveBetsBet | None:
    """The ``livebets_bets`` mirror row for ``bet_id`` (committed), or None."""
    sm = _get_session_maker()
    async with sm() as s:
        return (
            await s.execute(select(LiveBetsBet).where(LiveBetsBet.bet_id == bet_id))
        ).scalar_one_or_none()


async def _transfers_for_bet(bet_id: UUID) -> list[Transfer]:
    """Transfers whose ``metadata->>'bet_id'`` matches (committed) — model on
    ``_audit_for_market`` (which uses ``AuditLog.payload['market_id'].astext``).
    Used to COUNT the ledger legs posted for a bet."""
    sm = _get_session_maker()
    async with sm() as s:
        return list(
            (
                await s.execute(
                    select(Transfer).where(
                        Transfer.transfer_metadata["bet_id"].astext == str(bet_id)
                    )
                )
            )
            .scalars()
            .all()
        )


async def _count_bets_table() -> int:
    """Row count of the deferred ``bets`` table — proves the bridge does NOT touch it.

    ``bets`` has no migration on this branch (0005 deferred); the bridge must not
    create or write it. If the table is absent we treat the count as 0 (untouched).
    """
    sm = _get_session_maker()
    async with sm() as s:
        exists = (await s.execute(text("SELECT to_regclass('public.bets')"))).scalar_one()
        if exists is None:
            return 0
        return (await s.execute(text("SELECT count(*) FROM bets"))).scalar_one()


# =========================================================================== #
# placed -> won — wallet up by winnings, escrow nets to zero, winnings from
# house_promo, mirror WON/settled_at, bets table untouched.
# =========================================================================== #
async def test_placed_then_won_pays_stake_and_winnings_escrow_nets_to_zero() -> None:
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    bet_id = uuid4()
    client = FakeLiveBetsClient()
    stake = Decimal("20.0000")
    payout = Decimal("50.0000")  # winnings = 30

    escrow_before = await _livebets_escrow_balance()
    promo_before = await _balance(HOUSE_PROMO_ACCOUNT_ID)
    bets_before = await _count_bets_table()

    # PLACED — debit wallet -> escrow (stake).
    client.set_bet(bet_id, status=LIVEBETS_PENDING, stake=stake, payout=None)
    sm = _get_session_maker()
    async with sm() as s:
        placed = await LiveBetsBridge.record_placed(
            s, user=_user(user_id), bet_id=bet_id, client=client
        )
    assert placed.applied is True
    assert placed.status == LIVEBETS_PENDING
    assert await _balance(wallet_id) == Decimal("80.0000")  # 100 - 20 stake
    assert await _livebets_escrow_balance() - escrow_before == stake  # escrow +stake

    # WON — return stake (escrow -> wallet) + winnings (house_promo -> wallet).
    client.set_bet(bet_id, status=LIVEBETS_WON, stake=stake, payout=payout)
    async with sm() as s:
        settled = await LiveBetsBridge.record_settled(
            s, user=_user(user_id), bet_id=bet_id, client=client
        )
    assert settled.applied is True
    assert settled.status == LIVEBETS_WON

    # Wallet net: 100 - 20 + 20 + 30 = 130.
    assert await _balance(wallet_id) == Decimal("130.0000")
    # Escrow back to its starting balance across the full placed->won cycle.
    assert await _livebets_escrow_balance() == escrow_before
    # Winnings (payout - stake = 30) came OUT of house_promo.
    assert promo_before - await _balance(HOUSE_PROMO_ACCOUNT_ID) == Decimal("30.0000")
    # Mirror row WON with settled_at set.
    mirror = await _mirror_row(bet_id)
    assert mirror is not None
    assert mirror.status == LIVEBETS_WON
    assert mirror.settled_at is not None
    assert mirror.stake == stake
    # Two ledger legs for the WON cycle's settle (stake-return + winnings) + the
    # placed leg = 3 transfers carrying this bet_id.
    assert len(await _transfers_for_bet(bet_id)) == 3
    # The deferred bets table is untouched.
    assert await _count_bets_table() == bets_before


# =========================================================================== #
# placed -> lost — wallet down by stake, escrow nets to zero, house_revenue
# gains the stake, mirror LOST.
# =========================================================================== #
async def test_placed_then_lost_sweeps_stake_to_house_revenue_escrow_nets_to_zero() -> None:
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    bet_id = uuid4()
    client = FakeLiveBetsClient()
    stake = Decimal("35.0000")

    escrow_before = await _livebets_escrow_balance()
    revenue_before = await _balance(HOUSE_REVENUE_ACCOUNT_ID)

    client.set_bet(bet_id, status=LIVEBETS_PENDING, stake=stake)
    sm = _get_session_maker()
    async with sm() as s:
        await LiveBetsBridge.record_placed(s, user=_user(user_id), bet_id=bet_id, client=client)

    client.set_bet(bet_id, status=LIVEBETS_LOST, stake=stake)
    async with sm() as s:
        settled = await LiveBetsBridge.record_settled(
            s, user=_user(user_id), bet_id=bet_id, client=client
        )
    assert settled.applied is True
    assert settled.status == LIVEBETS_LOST

    # Wallet down by the full stake (no return on a loss).
    assert await _balance(wallet_id) == Decimal("65.0000")  # 100 - 35
    # Escrow nets to zero over placed->lost.
    assert await _livebets_escrow_balance() == escrow_before
    # The lost stake became house revenue.
    assert await _balance(HOUSE_REVENUE_ACCOUNT_ID) - revenue_before == stake
    mirror = await _mirror_row(bet_id)
    assert mirror is not None
    assert mirror.status == LIVEBETS_LOST
    assert mirror.settled_at is not None


# =========================================================================== #
# placed -> REFUNDED and placed -> VOIDED — both return the stake to the wallet
# (the two REAL refund statuses; there is NO ``VOID``). Parametrized to cover both.
# =========================================================================== #
@pytest.mark.parametrize("refund_status", [LIVEBETS_REFUNDED, LIVEBETS_VOIDED])
async def test_placed_then_refund_returns_stake_escrow_nets_to_zero(refund_status: str) -> None:
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    bet_id = uuid4()
    client = FakeLiveBetsClient()
    stake = Decimal("40.0000")

    escrow_before = await _livebets_escrow_balance()
    promo_before = await _balance(HOUSE_PROMO_ACCOUNT_ID)
    revenue_before = await _balance(HOUSE_REVENUE_ACCOUNT_ID)

    client.set_bet(bet_id, status=LIVEBETS_PENDING, stake=stake)
    sm = _get_session_maker()
    async with sm() as s:
        await LiveBetsBridge.record_placed(s, user=_user(user_id), bet_id=bet_id, client=client)
    assert await _balance(wallet_id) == Decimal("60.0000")  # 100 - 40 staked

    client.set_bet(bet_id, status=refund_status, stake=stake)
    async with sm() as s:
        settled = await LiveBetsBridge.record_settled(
            s, user=_user(user_id), bet_id=bet_id, client=client
        )
    assert settled.applied is True
    assert settled.status == refund_status

    # Wallet whole again (net zero over placed->refund).
    assert await _balance(wallet_id) == Decimal("100.0000")
    # Escrow nets to zero; refunds touch neither house account.
    assert await _livebets_escrow_balance() == escrow_before
    assert await _balance(HOUSE_PROMO_ACCOUNT_ID) == promo_before
    assert await _balance(HOUSE_REVENUE_ACCOUNT_ID) == revenue_before
    mirror = await _mirror_row(bet_id)
    assert mirror is not None
    assert mirror.status == refund_status
    assert mirror.settled_at is not None


# =========================================================================== #
# WON with payout == stake — only the stake-return leg posts (no zero-amount
# winnings entry), house_promo untouched.
# =========================================================================== #
async def test_won_with_no_winnings_posts_only_stake_return_leg() -> None:
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    bet_id = uuid4()
    client = FakeLiveBetsClient()
    stake = Decimal("25.0000")

    escrow_before = await _livebets_escrow_balance()
    promo_before = await _balance(HOUSE_PROMO_ACCOUNT_ID)

    client.set_bet(bet_id, status=LIVEBETS_PENDING, stake=stake)
    sm = _get_session_maker()
    async with sm() as s:
        await LiveBetsBridge.record_placed(s, user=_user(user_id), bet_id=bet_id, client=client)

    # payout == stake -> winnings (payout - stake) == 0 -> the winnings leg is skipped.
    client.set_bet(bet_id, status=LIVEBETS_WON, stake=stake, payout=stake)
    async with sm() as s:
        settled = await LiveBetsBridge.record_settled(
            s, user=_user(user_id), bet_id=bet_id, client=client
        )
    assert settled.applied is True

    # Wallet restored to exactly the starting balance (stake back, no winnings).
    assert await _balance(wallet_id) == Decimal("100.0000")
    assert await _livebets_escrow_balance() == escrow_before
    # house_promo NEVER funded a zero/negative winnings leg (CHECK amount > 0 never tripped).
    assert await _balance(HOUSE_PROMO_ACCOUNT_ID) == promo_before
    # Exactly TWO transfers carry this bet_id: the placed leg + the single stake-return
    # leg (NO winnings leg).
    assert len(await _transfers_for_bet(bet_id)) == 2


# =========================================================================== #
# Idempotency PRIMARY guard — duplicate record_placed is a no-op (applied=False,
# no second transfer, wallet unchanged from the single debit).
# =========================================================================== #
async def test_duplicate_placed_is_noop_primary_guard() -> None:
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    bet_id = uuid4()
    client = FakeLiveBetsClient()
    stake = Decimal("20.0000")
    client.set_bet(bet_id, status=LIVEBETS_PENDING, stake=stake)

    sm = _get_session_maker()
    async with sm() as s1:
        first = await LiveBetsBridge.record_placed(
            s1, user=_user(user_id), bet_id=bet_id, client=client
        )
    assert first.applied is True
    assert await _balance(wallet_id) == Decimal("80.0000")
    legs_after_first = len(await _transfers_for_bet(bet_id))
    assert legs_after_first == 1  # just the placed leg

    # Replay on a SEPARATE session — the mirror row already exists (PENDING) so the
    # primary guard short-circuits: no second transfer, balance unchanged.
    async with sm() as s2:
        second = await LiveBetsBridge.record_placed(
            s2, user=_user(user_id), bet_id=bet_id, client=client
        )
    assert second.applied is False
    assert await _balance(wallet_id) == Decimal("80.0000")  # unchanged
    assert len(await _transfers_for_bet(bet_id)) == legs_after_first  # no new leg


# =========================================================================== #
# Idempotency PRIMARY guard — duplicate record_settled is a no-op (no extra
# entries, balances unchanged, applied=False).
# =========================================================================== #
async def test_duplicate_settled_is_noop_primary_guard() -> None:
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    bet_id = uuid4()
    client = FakeLiveBetsClient()
    stake = Decimal("30.0000")
    payout = Decimal("70.0000")  # winnings 40

    client.set_bet(bet_id, status=LIVEBETS_PENDING, stake=stake)
    sm = _get_session_maker()
    async with sm() as s:
        await LiveBetsBridge.record_placed(s, user=_user(user_id), bet_id=bet_id, client=client)

    client.set_bet(bet_id, status=LIVEBETS_WON, stake=stake, payout=payout)
    async with sm() as s1:
        first = await LiveBetsBridge.record_settled(
            s1, user=_user(user_id), bet_id=bet_id, client=client
        )
    assert first.applied is True
    balance_after_first = await _balance(wallet_id)
    legs_after_first = len(await _transfers_for_bet(bet_id))

    # Replay the settle on a SEPARATE session — mirror row is already WON (non-PENDING),
    # so the primary guard short-circuits: no extra legs, balance unchanged.
    async with sm() as s2:
        second = await LiveBetsBridge.record_settled(
            s2, user=_user(user_id), bet_id=bet_id, client=client
        )
    assert second.applied is False
    assert await _balance(wallet_id) == balance_after_first
    assert len(await _transfers_for_bet(bet_id)) == legs_after_first


# =========================================================================== #
# Idempotency SECONDARY (23505) guard — the two-leg WON path. Pre-insert a
# colliding per-leg idempotency_key (``livebets:{bet_id}:settled:stake``) while the
# mirror row is STILL PENDING (so the primary guard does NOT short-circuit), then
# call record_settled (WON): the bridge must catch the 23505, return applied=False,
# and leave escrow + wallet consistent with NO half-applied settle. This is the ONLY
# test that exercises the per-leg-key collision on the two-leg WON case (M3).
# =========================================================================== #
async def test_won_secondary_idempotency_key_collision_is_caught() -> None:
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    bet_id = uuid4()
    client = FakeLiveBetsClient()
    stake = Decimal("20.0000")
    payout = Decimal("50.0000")

    # PLACED normally — mirror row PENDING, wallet -> 80, escrow +stake.
    client.set_bet(bet_id, status=LIVEBETS_PENDING, stake=stake)
    sm = _get_session_maker()
    async with sm() as s:
        await LiveBetsBridge.record_placed(s, user=_user(user_id), bet_id=bet_id, client=client)
    wallet_after_placed = await _balance(wallet_id)
    escrow_after_placed = await _livebets_escrow_balance()
    assert wallet_after_placed == Decimal("80.0000")

    # POISON the WON stake-return leg's key directly (a bare transfer row, no entries /
    # no balance move) while the mirror row is STILL PENDING — so the primary guard does
    # not short-circuit and the settle actually attempts to post, hitting the UNIQUE
    # transfers.idempotency_key on its FIRST leg.
    collision_key = settled_stake_idempotency_key(bet_id)
    async with sm() as s, s.begin():
        await s.execute(
            text("INSERT INTO transfers (id, kind, idempotency_key) VALUES (:id, :k, :key)"),
            {"id": uuid4(), "k": "poison", "key": collision_key},
        )

    # Now WON — the stake-return leg's key collides -> 23505 -> caught -> applied=False.
    client.set_bet(bet_id, status=LIVEBETS_WON, stake=stake, payout=payout)
    async with sm() as s:
        result = await LiveBetsBridge.record_settled(
            s, user=_user(user_id), bet_id=bet_id, client=client
        )
    assert result.applied is False
    assert result.status == LIVEBETS_WON

    # NO half-applied settle: the whole begin() block rolled back, so wallet + escrow are
    # exactly where the placement left them, and the mirror row is STILL PENDING.
    assert await _balance(wallet_id) == wallet_after_placed
    assert await _livebets_escrow_balance() == escrow_after_placed
    mirror = await _mirror_row(bet_id)
    assert mirror is not None
    assert mirror.status == LIVEBETS_PENDING
    assert mirror.settled_at is None
    # Only the placed leg + the poison row carry/own a related transfer; no settle legs
    # with this bet_id metadata were committed.
    settle_legs = [t for t in await _transfers_for_bet(bet_id) if t.kind != "livebets_placed"]
    assert settle_legs == []


# =========================================================================== #
# Verification rejects mismatch — record_placed on a non-PENDING live-bets bet
# raises LiveBetsVerificationError with NO ledger entry and NO mirror row.
# =========================================================================== #
async def test_record_placed_rejects_non_pending_bet() -> None:
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    bet_id = uuid4()
    client = FakeLiveBetsClient()
    # live-bets says this bet is already WON — placed must be rejected.
    client.set_bet(bet_id, status=LIVEBETS_WON, stake=Decimal("20.0000"), payout=Decimal("50.0000"))

    sm = _get_session_maker()
    with pytest.raises(LiveBetsVerificationError):
        async with sm() as s:
            await LiveBetsBridge.record_placed(s, user=_user(user_id), bet_id=bet_id, client=client)

    # Zero ledger effect: wallet untouched, no mirror row, no transfers for the bet.
    assert await _balance(wallet_id) == Decimal("100.0000")
    assert await _mirror_row(bet_id) is None
    assert await _transfers_for_bet(bet_id) == []


# =========================================================================== #
# Verification rejects mismatch — record_settled while live-bets still says
# PENDING raises, with no ledger entry (the bet is mirrored PENDING first).
# =========================================================================== #
async def test_record_settled_rejects_still_pending_bet() -> None:
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    bet_id = uuid4()
    client = FakeLiveBetsClient()
    stake = Decimal("20.0000")

    client.set_bet(bet_id, status=LIVEBETS_PENDING, stake=stake)
    sm = _get_session_maker()
    async with sm() as s:
        await LiveBetsBridge.record_placed(s, user=_user(user_id), bet_id=bet_id, client=client)
    wallet_after_placed = await _balance(wallet_id)
    legs_after_placed = len(await _transfers_for_bet(bet_id))

    # live-bets STILL says PENDING (not a terminal status) -> settle must reject.
    with pytest.raises(LiveBetsVerificationError):
        async with sm() as s:
            await LiveBetsBridge.record_settled(
                s, user=_user(user_id), bet_id=bet_id, client=client
            )

    # No settle leg posted; mirror row still PENDING; wallet unchanged.
    assert await _balance(wallet_id) == wallet_after_placed
    assert len(await _transfers_for_bet(bet_id)) == legs_after_placed
    mirror = await _mirror_row(bet_id)
    assert mirror is not None
    assert mirror.status == LIVEBETS_PENDING


# =========================================================================== #
# Verification rejects mismatch — a WON settle with NO payout field raises, with
# no ledger entry (the bridge will not guess winnings).
# =========================================================================== #
async def test_record_settled_won_without_payout_rejected() -> None:
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    bet_id = uuid4()
    client = FakeLiveBetsClient()
    stake = Decimal("20.0000")

    client.set_bet(bet_id, status=LIVEBETS_PENDING, stake=stake)
    sm = _get_session_maker()
    async with sm() as s:
        await LiveBetsBridge.record_placed(s, user=_user(user_id), bet_id=bet_id, client=client)
    wallet_after_placed = await _balance(wallet_id)
    escrow_after_placed = await _livebets_escrow_balance()
    legs_after_placed = len(await _transfers_for_bet(bet_id))

    # WON but payout is absent (None) -> verification failure, no winnings guess.
    client.set_bet(bet_id, status=LIVEBETS_WON, stake=stake, payout=None)
    with pytest.raises(LiveBetsVerificationError):
        async with sm() as s:
            await LiveBetsBridge.record_settled(
                s, user=_user(user_id), bet_id=bet_id, client=client
            )

    # Zero ledger effect for the settle; mirror row still PENDING.
    assert await _balance(wallet_id) == wallet_after_placed
    assert await _livebets_escrow_balance() == escrow_after_placed
    assert len(await _transfers_for_bet(bet_id)) == legs_after_placed
    mirror = await _mirror_row(bet_id)
    assert mirror is not None
    assert mirror.status == LIVEBETS_PENDING


# =========================================================================== #
# Server-side stake authority — the amount that moves comes from live-bets, never
# the request. The request carries ONLY a bet_id; get_bet is seeded with stake=S
# and EXACTLY S moves wallet->escrow (and back on win). Proven for both legs of a
# WON cycle.
# =========================================================================== #
async def test_stake_authority_is_server_side_not_request() -> None:
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    bet_id = uuid4()
    client = FakeLiveBetsClient()
    server_stake = Decimal("37.5000")  # the live-bets authoritative stake
    payout = Decimal("60.0000")  # winnings 22.5

    escrow_before = await _livebets_escrow_balance()
    promo_before = await _balance(HOUSE_PROMO_ACCOUNT_ID)

    # The "request" only knows bet_id; the stake authority is get_bet's stake.
    client.set_bet(bet_id, status=LIVEBETS_PENDING, stake=server_stake)
    sm = _get_session_maker()
    async with sm() as s:
        await LiveBetsBridge.record_placed(s, user=_user(user_id), bet_id=bet_id, client=client)
    # EXACTLY server_stake moved wallet -> escrow.
    assert await _balance(wallet_id) == Decimal("100.0000") - server_stake
    assert await _livebets_escrow_balance() - escrow_before == server_stake
    # The mirror row captured the server-side stake (used as the settle authority).
    mirror = await _mirror_row(bet_id)
    assert mirror is not None
    assert mirror.stake == server_stake

    client.set_bet(bet_id, status=LIVEBETS_WON, stake=server_stake, payout=payout)
    async with sm() as s:
        await LiveBetsBridge.record_settled(s, user=_user(user_id), bet_id=bet_id, client=client)
    # Wallet net = 100 - 37.5 + 37.5 + 22.5 = 122.5; escrow nets to zero; winnings
    # (22.5) funded by house_promo.
    assert await _balance(wallet_id) == Decimal("122.5000")
    assert await _livebets_escrow_balance() == escrow_before
    assert promo_before - await _balance(HOUSE_PROMO_ACCOUNT_ID) == Decimal("22.5000")
