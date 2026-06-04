"""Bloque 4 — DB-backed bet placement (via BetService.place_bet) + open portfolio.

Bets go through ``BetService.place_bet`` (the validated path: liability account +
double-entry ledger move), never a hand-written INSERT. Verified through the real
``BetService.get_portfolio``: pre-resolution every placed bet is an OPEN position
whose potential payout (stake / odds, odds<1) strictly exceeds the stake.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.bets.service import BetService
from app.db.session import _get_session_maker
from bin.seed_demo import SeedConfig, seed_bets, seed_markets, seed_users

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine:
    return engine


async def test_seed_bets_places_bets_and_funds_open_portfolio() -> None:
    """Every placed bet becomes an OPEN portfolio position with payout > stake."""
    cfg = SeedConfig(
        n_users=4, n_markets=3, n_resolved_markets=0, email_domain="seed-bets.demo.xpredict"
    )
    users = await seed_users(cfg)
    markets = await seed_markets(cfg)

    count = await seed_bets(cfg, users, markets)
    assert count > 0

    sm = _get_session_maker()
    total_open = 0
    for u in users:
        async with sm() as s:
            pf = await BetService.get_portfolio(s, user_id=u.id)
            total_open += len(pf.open)
            assert len(pf.settled) == 0  # nothing resolved yet
            for pos in pf.open:
                # potential payout = stake / odds (odds < 1) → strictly > stake.
                assert pos.potential_payout > pos.stake
    # Every placed bet is an open position pre-resolution.
    assert total_open == count
