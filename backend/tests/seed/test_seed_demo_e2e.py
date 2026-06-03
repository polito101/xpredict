"""Bloque 7 — end-to-end seed orchestration + the acceptance check.

The headline verifiable (prompt): run the seed and assert markets > 0, settled
bets > 0, odds history present, and reconcile_wallets reports drift 0 after the
seed. The reconcile is asserted BASELINE-RELATIVE (the seed must not INCREASE the
drift count) — the repo's idiomatic pattern (test_reconcile.py), robust to drift
other integration tests leak into the shared session-scoped container.

Also covers the idempotency guard (a second seed is blocked) and the --reset CLI
path (wipe + repopulate).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select

from app.bets.models import Bet
from app.db.session import _get_session_maker
from app.markets.models import Market
from app.markets.service import MarketService
from app.wallet.reconcile import _reconcile_async
from bin.seed_demo import AlreadySeeded, SeedConfig, main, reset_demo, seed_demo

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine:
    return engine


async def _count_settled_bets() -> int:
    sm = _get_session_maker()
    async with sm() as s:
        return int(
            (
                await s.execute(
                    select(func.count())
                    .select_from(Bet)
                    .where(Bet.status.in_(("SETTLED_WON", "SETTLED_LOST")))
                )
            ).scalar_one()
        )


async def test_seed_demo_populates_and_reconciles_clean() -> None:
    """The acceptance check: a full seed fills the player surfaces AND leaves the
    ledger consistent (reconcile adds no drift — nothing bypassed the services)."""
    cfg = SeedConfig(
        n_users=4, n_markets=4, n_resolved_markets=2, email_domain="seed-e2e.demo.xpredict"
    )

    baseline = await _reconcile_async()
    settled_before = await _count_settled_bets()

    result = await seed_demo(cfg)

    # Markets created, bets settled, odds history present.
    assert result.markets > 0
    assert await _count_settled_bets() > settled_before  # the seed settled bets
    assert result.odds_snapshots > 0
    assert result.open_market_slugs  # at least one OPEN market for a live chart

    # A real price-history chart renders for an OPEN market (>=2 points).
    sm = _get_session_maker()
    async with sm() as s:
        resp = await MarketService.price_history(s, result.open_market_slugs[0], "30d")
        assert len(resp.points) >= 2

    # reconcile_wallets reports NO new drift after the seed → every seeded account
    # is ledger-backed (the seed never bypassed the wallet/settlement services).
    after = await _reconcile_async()
    assert after["drift_count"] == baseline["drift_count"]


async def test_seed_demo_guard_blocks_double_seed() -> None:
    """A second seed without --reset is blocked (the demo admin is the marker)."""
    cfg = SeedConfig(
        n_users=2, n_markets=2, n_resolved_markets=0, email_domain="seed-guard.demo.xpredict"
    )
    await seed_demo(cfg)
    with pytest.raises(AlreadySeeded):
        await seed_demo(cfg)


async def test_main_reset_wipes_and_repopulates() -> None:
    """``main(["--reset"])`` wipes then re-seeds; demo data is present afterwards."""
    cfg = SeedConfig(
        n_users=2, n_markets=2, n_resolved_markets=1, email_domain="seed-main.demo.xpredict"
    )
    await reset_demo()  # clean slate first (global)
    await seed_demo(cfg)

    rc = await main(["--reset"], cfg=cfg)
    assert rc == 0

    sm = _get_session_maker()
    async with sm() as s:
        markets = (await s.execute(select(func.count()).select_from(Market))).scalar_one()
    assert markets > 0
