"""LiveBetsBridge — security & robustness hardening (LB-A review fixes BL-01, WR-01..03).

Integration tests (testcontainers), hermetic (``FakeLiveBetsClient`` only — no network).
Mirrors ``test_livebets_bridge.py`` EXACTLY: the ``engine`` fixture runs ``alembic
upgrade head`` (so migration ``0011`` provides ``livebets_escrow`` + ``livebets_bets``),
and the committed-session pattern is used because ``LiveBetsBridge`` owns its
``session.begin()`` unit of work. Shared singletons (``house_promo`` /
``house_revenue`` / ``livebets_escrow``) are asserted via BEFORE/AFTER deltas; per-test
wallets and ``bet_id``s use fresh ``uuid4()``.

Covered (all assert ZERO ledger effect on rejection — no transfers, mirror untouched,
balances unchanged):
  - BL-01: ``record_settled`` by a NON-owner is rejected (``LiveBetsOwnershipError``)
    with no payout — the IDOR cross-player payout-theft guard.
  - BL-01 (route): the ``POST /bets/{id}/settled`` route maps a non-owner to HTTP 404.
  - WR-01: a NaN / Infinity stake or payout is rejected (no posting).
  - WR-02: a stake above ``BET_MAX_STAKE`` (and below ``BET_MIN_STAKE``) is rejected at
    placement (no debit).
  - WR-03: a settle whose live-bets ``stake`` != the mirrored stake is rejected (no posting).
"""

from __future__ import annotations

import types
from collections.abc import AsyncGenerator
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.auth.deps import current_active_player
from app.core.config import get_settings
from app.db.session import _get_session_maker, get_async_session
from app.integrations.livebets.constants import (
    LIVEBETS_ESCROW_ACCOUNT_ID,
    LIVEBETS_PENDING,
    LIVEBETS_WON,
)
from app.integrations.livebets.models import LiveBetsBet
from app.integrations.livebets.router import get_livebets_client
from app.integrations.livebets.service import (
    LiveBetsBridge,
    LiveBetsOwnershipError,
    LiveBetsVerificationError,
)
from app.main import app
from app.wallet.constants import (
    HOUSE_PROMO_ACCOUNT_ID,
    KIND_USER_WALLET,
    OWNER_USER,
    PLAY_USD,
)
from app.wallet.models import Account, Transfer

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine:
    """Depend on ``engine`` (container, migrate, env rewrite) — mirrors test_livebets_bridge.py."""
    return engine


# --------------------------------------------------------------------------- #
# FakeLiveBetsClient — in-memory double of the bridge's reader slice (get_bet).
# A faithful copy of the bridge-test double (hermetic, no network). Stores the
# raw dict so a test can inject a NaN/Infinity payload that _safe_decimal must reject.
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
        stake: object,
        market_id: object | None = None,
        table_id: object | None = None,  # BetView has no table_id; kept for call-site parity
        payout: object | None = None,
    ) -> None:
        # REAL live-bets BetView shape (live_bets/api/routes/bets.py): id (NOT
        # bet_id), selection (NOT side), NO table_id, payout str|None. `stake` /
        # `payout` are stored raw so a test can inject a NaN/Infinity payload that
        # `_safe_decimal` must reject (WR-01).
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
    """A minimal ``user`` stand-in — the bridge only reads ``user.id``."""
    return types.SimpleNamespace(id=user_id)


# --------------------------------------------------------------------------- #
# Committed-session helpers (assert against committed state) — copied from
# test_livebets_bridge.py.
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
    return await _balance(LIVEBETS_ESCROW_ACCOUNT_ID)


async def _mirror_row(bet_id: UUID) -> LiveBetsBet | None:
    sm = _get_session_maker()
    async with sm() as s:
        return (
            await s.execute(select(LiveBetsBet).where(LiveBetsBet.bet_id == bet_id))
        ).scalar_one_or_none()


async def _transfers_for_bet(bet_id: UUID) -> list[Transfer]:
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


# =========================================================================== #
# BL-01 — a NON-owner settling another player's bet is rejected (IDOR guard),
# with ZERO ledger effect: no settle transfer, the mirror row stays PENDING,
# both wallets and escrow unchanged. This is the actual payout-theft vector.
# =========================================================================== #
async def test_record_settled_by_non_owner_is_rejected_no_ledger_effect() -> None:
    # Owner A places a winning-eligible bet; attacker B has their own wallet.
    owner_id, owner_wallet = await _seed_wallet(Decimal("100.0000"))
    attacker_id, attacker_wallet = await _seed_wallet(Decimal("100.0000"))
    bet_id = uuid4()
    client = FakeLiveBetsClient()
    stake = Decimal("20.0000")
    payout = Decimal("50.0000")  # winnings 30 — what B would try to steal

    # A places (claims the bet -> mirror.user_id == A).
    client.set_bet(bet_id, status=LIVEBETS_PENDING, stake=stake)
    sm = _get_session_maker()
    async with sm() as s:
        await LiveBetsBridge.record_placed(
            s, user=_user(owner_id), bet_id=bet_id, client=client
        )

    owner_wallet_after_placed = await _balance(owner_wallet)
    escrow_after_placed = await _livebets_escrow_balance()
    promo_after_placed = await _balance(HOUSE_PROMO_ACCOUNT_ID)
    legs_after_placed = len(await _transfers_for_bet(bet_id))

    # The bet is now WON in live-bets; attacker B tries to settle (and be paid).
    client.set_bet(bet_id, status=LIVEBETS_WON, stake=stake, payout=payout)
    with pytest.raises(LiveBetsOwnershipError):
        async with sm() as s:
            await LiveBetsBridge.record_settled(
                s, user=_user(attacker_id), bet_id=bet_id, client=client
            )

    # ZERO ledger effect: no settle leg posted; mirror row still PENDING (untouched);
    # attacker's wallet untouched; owner's wallet untouched; escrow + house_promo whole.
    assert len(await _transfers_for_bet(bet_id)) == legs_after_placed
    mirror = await _mirror_row(bet_id)
    assert mirror is not None
    assert mirror.status == LIVEBETS_PENDING
    assert mirror.settled_at is None
    assert mirror.user_id == owner_id  # ownership unchanged
    assert await _balance(attacker_wallet) == Decimal("100.0000")  # attacker not credited
    assert await _balance(owner_wallet) == owner_wallet_after_placed
    assert await _livebets_escrow_balance() == escrow_after_placed
    assert await _balance(HOUSE_PROMO_ACCOUNT_ID) == promo_after_placed


# =========================================================================== #
# WR-02 — a stake above BET_MAX_STAKE (and below BET_MIN_STAKE) is rejected at
# placement, BEFORE any debit: no mirror row, no transfer, wallet unchanged.
# =========================================================================== #
@pytest.mark.parametrize("kind", ["above_max", "below_min"])
async def test_record_placed_rejects_out_of_band_stake_no_debit(kind: str) -> None:
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    bet_id = uuid4()
    client = FakeLiveBetsClient()
    settings = get_settings()
    if kind == "above_max":
        stake = settings.BET_MAX_STAKE + Decimal("1")
    else:
        # Below the floor but still > 0 (so it is a band rejection, not the <=0 path).
        stake = settings.BET_MIN_STAKE / Decimal("2")
        assert stake > 0

    escrow_before = await _livebets_escrow_balance()
    client.set_bet(bet_id, status=LIVEBETS_PENDING, stake=stake)

    sm = _get_session_maker()
    with pytest.raises(LiveBetsVerificationError):
        async with sm() as s:
            await LiveBetsBridge.record_placed(
                s, user=_user(user_id), bet_id=bet_id, client=client
            )

    # No debit, no mirror row, no transfer, escrow untouched.
    assert await _balance(wallet_id) == Decimal("100.0000")
    assert await _mirror_row(bet_id) is None
    assert await _transfers_for_bet(bet_id) == []
    assert await _livebets_escrow_balance() == escrow_before


async def test_record_placed_accepts_stake_at_band_boundaries() -> None:
    """The band is INCLUSIVE — BET_MIN_STAKE and BET_MAX_STAKE both place cleanly.

    Guards against an off-by-one in the WR-02 bound (``<=`` not ``<``). Uses the floor
    (a fresh wallet funded to exactly cover it) so the assertion is exact and cheap.
    """
    settings = get_settings()
    min_stake = settings.BET_MIN_STAKE
    user_id, wallet_id = await _seed_wallet(min_stake)
    bet_id = uuid4()
    client = FakeLiveBetsClient()

    client.set_bet(bet_id, status=LIVEBETS_PENDING, stake=min_stake)
    sm = _get_session_maker()
    async with sm() as s:
        placed = await LiveBetsBridge.record_placed(
            s, user=_user(user_id), bet_id=bet_id, client=client
        )
    assert placed.applied is True
    assert await _balance(wallet_id) == Decimal("0.0000")  # exactly the min stake debited
    mirror = await _mirror_row(bet_id)
    assert mirror is not None
    assert mirror.stake == min_stake


# =========================================================================== #
# WR-01 — a NaN / Infinity stake is rejected at placement (parse-time), and a
# NaN / Infinity payout on a WON settle is rejected, both with ZERO ledger effect.
# (Without the _safe_decimal is_finite() guard, NaN would slip past the None guard
# and corrupt the winnings math.)
# =========================================================================== #
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "NaN", "Infinity"])
async def test_record_placed_rejects_non_finite_stake_no_debit(bad: object) -> None:
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    bet_id = uuid4()
    client = FakeLiveBetsClient()
    escrow_before = await _livebets_escrow_balance()

    # A non-finite stake -> _safe_decimal returns None -> parse_verified_bet raises
    # ValueError ("missing/invalid 'stake'") BEFORE any session.begin() / debit.
    client.set_bet(bet_id, status=LIVEBETS_PENDING, stake=bad)
    sm = _get_session_maker()
    with pytest.raises(ValueError):
        async with sm() as s:
            await LiveBetsBridge.record_placed(
                s, user=_user(user_id), bet_id=bet_id, client=client
            )

    assert await _balance(wallet_id) == Decimal("100.0000")
    assert await _mirror_row(bet_id) is None
    assert await _transfers_for_bet(bet_id) == []
    assert await _livebets_escrow_balance() == escrow_before


@pytest.mark.parametrize("bad_payout", [float("nan"), float("inf"), "NaN", "Infinity"])
async def test_record_settled_won_rejects_non_finite_payout_no_posting(bad_payout: object) -> None:
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    bet_id = uuid4()
    client = FakeLiveBetsClient()
    stake = Decimal("20.0000")

    # Place cleanly first (finite stake).
    client.set_bet(bet_id, status=LIVEBETS_PENDING, stake=stake)
    sm = _get_session_maker()
    async with sm() as s:
        await LiveBetsBridge.record_placed(
            s, user=_user(user_id), bet_id=bet_id, client=client
        )
    wallet_after_placed = await _balance(wallet_id)
    escrow_after_placed = await _livebets_escrow_balance()
    promo_after_placed = await _balance(HOUSE_PROMO_ACCOUNT_ID)
    legs_after_placed = len(await _transfers_for_bet(bet_id))

    # WON with a non-finite payout -> _safe_decimal -> None -> treated as "no payout"
    # -> the WON-without-payout verification failure (no winnings guess, no posting).
    client.set_bet(bet_id, status=LIVEBETS_WON, stake=stake, payout=bad_payout)
    with pytest.raises(LiveBetsVerificationError):
        async with sm() as s:
            await LiveBetsBridge.record_settled(
                s, user=_user(user_id), bet_id=bet_id, client=client
            )

    # Zero ledger effect for the settle; mirror row still PENDING.
    assert await _balance(wallet_id) == wallet_after_placed
    assert await _livebets_escrow_balance() == escrow_after_placed
    assert await _balance(HOUSE_PROMO_ACCOUNT_ID) == promo_after_placed
    assert len(await _transfers_for_bet(bet_id)) == legs_after_placed
    mirror = await _mirror_row(bet_id)
    assert mirror is not None
    assert mirror.status == LIVEBETS_PENDING


# =========================================================================== #
# WR-03 — a settle whose live-bets ``stake`` differs from the mirrored (placement)
# stake is rejected as a verification failure, with ZERO ledger effect. Stake drift
# between placement and settlement must NOT silently mis-pay winnings.
# =========================================================================== #
async def test_record_settled_rejects_stake_drift_no_posting() -> None:
    user_id, wallet_id = await _seed_wallet(Decimal("100.0000"))
    bet_id = uuid4()
    client = FakeLiveBetsClient()
    placed_stake = Decimal("20.0000")
    drifted_stake = Decimal("25.0000")  # live-bets reports a DIFFERENT stake at settle
    payout = Decimal("50.0000")

    # Place with the original stake -> mirror.stake == 20.
    client.set_bet(bet_id, status=LIVEBETS_PENDING, stake=placed_stake)
    sm = _get_session_maker()
    async with sm() as s:
        await LiveBetsBridge.record_placed(
            s, user=_user(user_id), bet_id=bet_id, client=client
        )
    wallet_after_placed = await _balance(wallet_id)
    escrow_after_placed = await _livebets_escrow_balance()
    promo_after_placed = await _balance(HOUSE_PROMO_ACCOUNT_ID)
    legs_after_placed = len(await _transfers_for_bet(bet_id))

    # WON, but live-bets now reports a drifted stake (25 != mirrored 20) -> reject.
    client.set_bet(bet_id, status=LIVEBETS_WON, stake=drifted_stake, payout=payout)
    with pytest.raises(LiveBetsVerificationError):
        async with sm() as s:
            await LiveBetsBridge.record_settled(
                s, user=_user(user_id), bet_id=bet_id, client=client
            )

    # Zero ledger effect for the settle; mirror row still PENDING; balances unchanged.
    assert await _balance(wallet_id) == wallet_after_placed
    assert await _livebets_escrow_balance() == escrow_after_placed
    assert await _balance(HOUSE_PROMO_ACCOUNT_ID) == promo_after_placed
    assert len(await _transfers_for_bet(bet_id)) == legs_after_placed
    mirror = await _mirror_row(bet_id)
    assert mirror is not None
    assert mirror.status == LIVEBETS_PENDING


# =========================================================================== #
# BL-01 (route) — the POST /api/live/bets/{id}/settled route maps a non-owner to
# HTTP 404 (not 403/409): "not your bet" is surfaced as not-found so a foreign
# bet's existence is never leaked (IDOR-safe). End-to-end through the FastAPI app
# against the real DB (committed sessions), with ZERO ledger effect.
# =========================================================================== #
class _Player:
    """Minimal authenticated-player stand-in — the route only reads ``id``."""

    def __init__(self, user_id: object) -> None:
        self.id = user_id


@pytest_asyncio.fixture(loop_scope="session")
async def api() -> AsyncGenerator[httpx.AsyncClient, None]:
    """httpx ASGITransport client against the real app (DB-touching route path).

    ``loop_scope="session"`` matches the module's session-scoped asyncio loop (set in
    ``pytestmark``) so the route's DB session shares the engine's event loop — avoiding
    the ``MultipleEventLoopsRequestedError`` a function-scoped client fixture triggers.
    """
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def _clear_overrides() -> AsyncGenerator[None, None]:
    """Reset FastAPI dependency overrides after every test — no cross-test leakage."""
    yield
    app.dependency_overrides.clear()


async def _committed_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a real committed-capable session (the bridge owns its own begin())."""
    sm = _get_session_maker()
    async with sm() as session:
        yield session


async def test_settled_route_non_owner_returns_404_no_ledger_effect(
    api: httpx.AsyncClient,
) -> None:
    owner_id, owner_wallet = await _seed_wallet(Decimal("100.0000"))
    attacker_id, attacker_wallet = await _seed_wallet(Decimal("100.0000"))
    bet_id = uuid4()
    client = FakeLiveBetsClient()
    stake = Decimal("20.0000")
    payout = Decimal("50.0000")

    # Owner A places (claims the bet) via the bridge directly (committed).
    client.set_bet(bet_id, status=LIVEBETS_PENDING, stake=stake)
    sm = _get_session_maker()
    async with sm() as s:
        await LiveBetsBridge.record_placed(
            s, user=_user(owner_id), bet_id=bet_id, client=client
        )
    owner_wallet_after_placed = await _balance(owner_wallet)
    escrow_after_placed = await _livebets_escrow_balance()
    legs_after_placed = len(await _transfers_for_bet(bet_id))

    # Wire the route: attacker B is the authed player; the bet is WON in live-bets;
    # the session + client deps use the real DB + fake client.
    client.set_bet(bet_id, status=LIVEBETS_WON, stake=stake, payout=payout)
    app.dependency_overrides[current_active_player] = lambda: _Player(attacker_id)
    app.dependency_overrides[get_livebets_client] = lambda: client
    app.dependency_overrides[get_async_session] = _committed_session

    r = await api.post(f"/api/live/bets/{bet_id}/settled")

    # 404 (IDOR-safe not-found), NOT 403/409.
    assert r.status_code == 404

    # ZERO ledger effect: no settle leg; mirror still PENDING/owned by A; wallets whole.
    assert len(await _transfers_for_bet(bet_id)) == legs_after_placed
    mirror = await _mirror_row(bet_id)
    assert mirror is not None
    assert mirror.status == LIVEBETS_PENDING
    assert mirror.user_id == owner_id
    assert await _balance(attacker_wallet) == Decimal("100.0000")
    assert await _balance(owner_wallet) == owner_wallet_after_placed
    assert await _livebets_escrow_balance() == escrow_after_placed
