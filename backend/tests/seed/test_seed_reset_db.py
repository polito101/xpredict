"""Bloque 6 — DB-backed demo reset (TRUNCATE the domain/ledger + re-seed house).

The ledger is append-only (transfers/entries DELETE is blocked by triggers), so the
only way to clear it is TRUNCATE — which does NOT fire the per-row triggers. After
the wipe, reset_demo re-seeds the two house-account singletons the ledger needs.

reset_demo is GLOBAL by design (TRUNCATE has no WHERE). It is safe in the shared
session-scoped container because every test re-seeds what it needs and reset puts
the house accounts back; this test asserts on the whole-DB counts deliberately.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select

from app.auth.models import User
from app.bets.models import Bet
from app.db.session import _get_session_maker
from app.markets.models import Market
from app.wallet.models import Account, Entry, Transfer
from bin.seed_demo import SeedConfig, reset_demo, seed_bets, seed_markets, seed_users

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine:
    return engine


async def _count(model: type) -> int:
    sm = _get_session_maker()
    async with sm() as s:
        return int((await s.execute(select(func.count()).select_from(model))).scalar_one())


async def test_reset_demo_wipes_dataset_and_reseeds_house() -> None:
    """After a populated seed, reset_demo empties the domain/ledger and restores the
    two house accounts (so the ledger precondition still holds)."""
    cfg = SeedConfig(
        n_users=2, n_markets=2, n_resolved_markets=1, email_domain="seed-reset.demo.xpredict"
    )
    users = await seed_users(cfg)
    markets = await seed_markets(cfg)
    await seed_bets(cfg, users, markets)

    # Sanity: there IS data to wipe.
    assert await _count(Market) > 0
    assert await _count(Bet) > 0

    await reset_demo()

    # Domain + ledger tables are empty.
    assert await _count(User) == 0
    assert await _count(Market) == 0
    assert await _count(Bet) == 0
    assert await _count(Transfer) == 0
    assert await _count(Entry) == 0

    # Exactly the two house-account singletons remain, with the funded promo balance.
    sm = _get_session_maker()
    async with sm() as s:
        accounts = list((await s.execute(select(Account))).scalars().all())
    assert {a.kind for a in accounts} == {"house_promo", "house_revenue"}
    promo = next(a for a in accounts if a.kind == "house_promo")
    assert promo.balance == Decimal("1000000000.0000")
    revenue = next(a for a in accounts if a.kind == "house_revenue")
    assert revenue.balance == Decimal("0")
