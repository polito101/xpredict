"""Bloque 3 — odds-history backfill so price-history charts render (no empty UI).

Verified through the REAL production read (``MarketService.price_history``): every
window (24h / 7d / 30d) must return >=2 YES points so the market-detail chart shows
a line, not the "not enough history yet" placeholder. The series converges to the
market's current YES odds. odds_snapshots are not money, so a direct insert is in
bounds (the ledger discipline is about transfers/entries).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.db.session import _get_session_maker
from app.markets.service import MarketService
from bin.seed_demo import SeedConfig, seed_markets, seed_odds_history

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine:
    return engine


async def test_seed_odds_history_fills_all_chart_windows() -> None:
    """Every chart window has >=2 YES points and the series ends at current odds."""
    cfg = SeedConfig(n_markets=2, n_resolved_markets=0, email_domain="seed-odds.demo.xpredict")
    markets = await seed_markets(cfg)

    count = await seed_odds_history(cfg, markets)
    assert count > 0

    sm = _get_session_maker()
    for m in markets:
        async with sm() as s:
            for window in ("24h", "7d", "30d"):
                resp = await MarketService.price_history(s, m.slug, window)
                # >=2 points → the frontend renders a real line, not the
                # "not enough history" placeholder (MKT-03).
                assert len(resp.points) >= 2, f"{window} window empty for {m.slug}"
            # The walk converges to the market's current YES odds (latest point).
            resp30 = await MarketService.price_history(s, m.slug, "30d")
            assert resp30.points[-1].probability == m.initial_odds_yes
