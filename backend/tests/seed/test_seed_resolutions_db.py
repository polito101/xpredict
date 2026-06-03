"""Bloque 5 — DB-backed market resolution (via SettlementService.resolve_market).

Resolution goes through the validated SettlementService (no hand-flipped status,
no hand-written ledger) so each settled bet posts the real payout legs and the P&L
is correct. We pass winning_outcome_id today; once Phase 12 persists the winner on
the Market model, the same call sets it for free (no seed change). Verified via the
real BetService.get_portfolio: settled positions carry realized P&L for BOTH a
winner (payout - stake > 0) and a loser (-stake).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from app.bets.service import BetService
from app.db.session import _get_session_maker
from app.markets.models import Market
from bin.seed_demo import SeedConfig, seed_bets, seed_markets, seed_resolutions, seed_users

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine:
    return engine


async def test_seed_resolutions_settles_bets_with_pnl() -> None:
    """Flagged markets become RESOLVED; their bets settle with winner + loser P&L."""
    cfg = SeedConfig(
        n_users=4, n_markets=3, n_resolved_markets=2, email_domain="seed-resolve.demo.xpredict"
    )
    users = await seed_users(cfg)
    markets = await seed_markets(cfg)
    await seed_bets(cfg, users, markets)

    resolved = await seed_resolutions(cfg, markets)
    assert resolved == 2  # exactly the flagged markets

    resolved_ids = {m.id for m in markets if m.resolve_to is not None}
    sm = _get_session_maker()
    for m in markets:
        async with sm() as s:
            status = (await s.execute(select(Market.status).where(Market.id == m.id))).scalar_one()
            assert status == ("RESOLVED" if m.id in resolved_ids else "OPEN")

    total_settled = 0
    won_seen = False
    lost_seen = False
    for u in users:
        async with sm() as s:
            pf = await BetService.get_portfolio(s, user_id=u.id)
            total_settled += len(pf.settled)
            for pos in pf.settled:
                if pos.won:
                    won_seen = True
                    assert pos.realized_pnl > 0
                else:
                    lost_seen = True
                    assert pos.realized_pnl == -pos.stake
    assert total_settled > 0
    # Both sides were bet on every market, so resolution yields winners AND losers.
    assert won_seen and lost_seen
