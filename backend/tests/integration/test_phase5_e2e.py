"""Phase 5 END-TO-END demo (integration) — the first demoable happy path.

bet -> admin resolve -> wallet credited -> portfolio P&L, exercised through the FastAPI app via
httpx with the REAL wired adapters (``HouseMarketReadAdapter`` + ``HouseMarketResolveAdapter``
over Phase 4's ``app/markets`` domain). Only AUTH is overridden (a verified player + an admin);
the market read/resolve ports are the real ones. This proves the full cross-phase integration:
Phase 4 markets <-> Phase 5 bets/settlement <-> Phase 3 double-entry ledger, on the integrated
migration chain (0001 -> 0002 -> 0003_phase4_markets -> 0004_phase3_wallet_ledger ->
0005_phase5_bets — the ``bets`` table comes from migration 0005, not a test fixture).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.auth.deps import current_active_admin, current_active_player
from app.db.session import _get_session_maker
from app.main import app
from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import Market, Outcome
from app.wallet.constants import KIND_USER_WALLET, OWNER_USER, PLAY_USD
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
    return engine


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(loop_scope="session")
async def api() -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class _Principal:
    def __init__(self, user_id: UUID, banned_at=None) -> None:
        self.id = user_id
        self.banned_at = banned_at


async def _create_open_house_market(yes_price: Decimal = Decimal("0.5")) -> tuple[UUID, UUID, UUID]:
    """Create an OPEN house market with YES/NO outcomes (committed); return ids."""
    sm = _get_session_maker()
    async with sm() as s, s.begin():
        market = Market(
            question="Will X happen by the deadline?",
            slug=f"will-x-{uuid4().hex[:10]}",
            resolution_criteria="Resolved per the official source.",
            deadline=datetime.now(UTC) + timedelta(days=1),
            source=MarketSourceEnum.HOUSE.value,
            status=MarketStatus.OPEN.value,
        )
        s.add(market)
        await s.flush()
        yes = Outcome(
            market_id=market.id, label="YES", initial_odds=yes_price, current_odds=yes_price
        )
        no_price = Decimal("1") - yes_price
        no = Outcome(market_id=market.id, label="NO", initial_odds=no_price, current_odds=no_price)
        s.add_all([yes, no])
        await s.flush()
        return market.id, yes.id, no.id


async def _seed_wallet(user_id: UUID, balance: Decimal) -> None:
    """Create a LEDGER-BACKED user_wallet for ``user_id`` at ``balance`` (committed).

    INSERTs at balance 0, then funds via the real ``WalletService.recharge`` (``house_promo ->
    wallet``, a proper ledger entry) so the committed wallet never registers as drift in the
    DB-wide ledger reconciler — which, on the session-scoped testcontainer, would otherwise leak
    into ``tests/settlement/test_event_*``. A bare-balance INSERT was the older shortcut.
    """
    wallet_id = uuid4()
    sm = _get_session_maker()
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO accounts (id, owner_type, owner_id, kind, currency, balance) "
                "VALUES (:id, :ot, :oid, :k, :c, :b)"
            ),
            {
                "id": wallet_id,
                "ot": OWNER_USER,
                "oid": user_id,
                "k": KIND_USER_WALLET,
                "c": PLAY_USD,
                "b": Decimal("0"),
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


async def _wallet_balance(user_id: UUID) -> Decimal:
    sm = _get_session_maker()
    async with sm() as s:
        return (
            await s.execute(
                select(Account.balance).where(
                    Account.owner_id == user_id, Account.kind == KIND_USER_WALLET
                )
            )
        ).scalar_one()


async def _market_status(market_id: UUID) -> str:
    sm = _get_session_maker()
    async with sm() as s:
        return (await s.execute(select(Market.status).where(Market.id == market_id))).scalar_one()


async def test_e2e_bet_resolve_wallet_portfolio(api: httpx.AsyncClient) -> None:
    player_id = uuid4()
    admin_id = uuid4()
    await _seed_wallet(player_id, Decimal("100.0000"))
    market_id, yes_id, _no_id = await _create_open_house_market(yes_price=Decimal("0.5"))

    # ---- 1) Player places a 40 bet on YES (real HouseMarketReadAdapter validates it) ----
    app.dependency_overrides[current_active_player] = lambda: _Principal(player_id)
    place = await api.post(
        "/bets",
        json={"market_id": str(market_id), "outcome_id": str(yes_id), "stake": "40.0000"},
    )
    assert place.status_code == 201, place.text
    assert place.json()["status"] == "PENDING"
    assert await _wallet_balance(player_id) == Decimal("60.0000")  # 100 - 40 stake

    # ---- 2) Portfolio shows the OPEN position with potential payout (40 / 0.5 = 80) ----
    pf_open = (await api.get("/bets/me/portfolio")).json()
    assert len(pf_open["open"]) == 1
    assert len(pf_open["settled"]) == 0
    assert Decimal(pf_open["open"][0]["potential_payout"]) == Decimal("80.0000")

    # ---- 3) Admin resolves YES (real HouseMarketResolveAdapter flips the market) ----
    app.dependency_overrides[current_active_admin] = lambda: _Principal(admin_id)
    resolve = await api.post(
        f"/admin/markets/{market_id}/resolve",
        json={"winning_outcome_id": str(yes_id), "justification": "Official source: YES"},
    )
    assert resolve.status_code == 200, resolve.text
    assert resolve.json()["bets_settled"] == 1
    assert Decimal(resolve.json()["total_payout"]) == Decimal("80.0000")

    # ---- 4) Wallet credited the full payout; market RESOLVED ----
    assert await _wallet_balance(player_id) == Decimal("140.0000")  # 60 + 80 payout
    assert await _market_status(market_id) == "RESOLVED"

    # ---- 5) Portfolio now shows the SETTLED position with realized P&L (+40) ----
    pf_settled = (await api.get("/bets/me/portfolio")).json()
    assert len(pf_settled["open"]) == 0
    assert len(pf_settled["settled"]) == 1
    won = pf_settled["settled"][0]
    assert won["won"] is True
    assert Decimal(won["payout"]) == Decimal("80.0000")
    assert Decimal(won["realized_pnl"]) == Decimal("40.0000")
