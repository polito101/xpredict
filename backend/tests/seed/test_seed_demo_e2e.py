"""Bloque 7 — end-to-end seed orchestration + the acceptance check.

The headline verifiable (prompt): run the seed and assert markets > 0, settled
bets > 0, odds history present, and reconcile_wallets reports drift 0 after the
seed. The reconcile is asserted BASELINE-RELATIVE (the seed must not INCREASE the
drift count) — the repo's idiomatic pattern (test_reconcile.py), robust to drift
other integration tests leak into the shared session-scoped container.

Also covers the idempotency guard (a second seed is blocked) and the --reset CLI
path (wipe + repopulate).

Phase 18 extends this with the multi-outcome event surface (DEMO-01..04): events
cover all four derived states, every featured category tab is filled above a
minimum, per-outcome odds history is non-flat, and --reset clears ``market_groups``
so a re-seed of the deterministic event slugs never collides. The pre-existing
standalone tests pin ``n_events=0`` to stay fast and focused on the binary spine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.bets.models import Bet
from app.catalog.service import CatalogService, child_status_of
from app.db.session import _get_session_maker
from app.markets.models import Market, MarketGroup, OddsSnapshot
from app.markets.service import MarketService
from app.settlement.event_service import derive_event_status
from app.wallet.reconcile import _reconcile_async
from bin.seed_demo import (
    _EVENT_TEMPLATES,
    FEATURED_CATEGORIES,
    MIN_ITEMS_PER_FEATURED_CATEGORY,
    AlreadySeeded,
    SeedConfig,
    _event_slug,
    main,
    reset_demo,
    seed_demo,
)

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


async def _event_statuses() -> set[str]:
    """Derived status of every ≥2-child event group currently in the DB."""
    sm = _get_session_maker()
    async with sm() as s:
        groups = (
            (
                await s.execute(
                    select(MarketGroup).options(
                        selectinload(MarketGroup.markets).selectinload(Market.outcomes)
                    )
                )
            )
            .scalars()
            .all()
        )
    statuses: set[str] = set()
    for group in groups:
        children = list(group.markets)
        if len(children) >= 2:
            statuses.add(derive_event_status([child_status_of(c) for c in children]))
    return statuses


async def test_seed_demo_populates_and_reconciles_clean() -> None:
    """The acceptance check: a full seed fills the player surfaces AND leaves the
    ledger consistent (reconcile adds no drift — nothing bypassed the services)."""
    cfg = SeedConfig(
        n_users=4,
        n_markets=4,
        n_resolved_markets=2,
        n_events=0,
        email_domain="seed-e2e.demo.xpredict",
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


async def test_seed_events_cover_all_four_states() -> None:
    """DEMO-01/02: the event set spans every derived status (open/partial/resolved/void)."""
    cfg = SeedConfig(
        n_users=6,
        n_markets=0,
        n_resolved_markets=0,
        n_events=7,
        email_domain="seed-events-states.demo.xpredict",
    )
    baseline = await _reconcile_async()

    result = await seed_demo(cfg)
    assert result.events == 7
    assert result.event_resolutions >= 3  # resolved + void + partial were advanced

    statuses = await _event_statuses()
    for expected in ("open", "partially_resolved", "resolved", "void"):
        assert expected in statuses, f"missing event state {expected!r}: {sorted(statuses)}"

    after = await _reconcile_async()
    assert after["drift_count"] == baseline["drift_count"]


async def test_seed_events_fill_featured_categories() -> None:
    """DEMO-03: every featured category tab renders and is filled above the minimum.

    Hermetic (resets first): the catalog reads the WHOLE DB, so resetting proves THIS
    seed fills every featured tab to the minimum on its own — borrowed rows from other
    tests in the shared container cannot mask a coverage regression.
    """
    cfg = SeedConfig(
        n_users=10,
        n_markets=15,
        n_resolved_markets=2,
        n_events=7,
        email_domain="seed-events-cats.demo.xpredict",
    )
    await reset_demo()  # clean slate so the >=2-per-tab assertion is on this seed alone
    baseline = await _reconcile_async()

    result = await seed_demo(cfg)
    assert result.events == 7

    sm = _get_session_maker()
    async with sm() as s:
        categories = await CatalogService.list_categories(s)
        for category in FEATURED_CATEGORIES:
            assert category in categories, f"featured category missing a tab: {category!r}"
        for category in FEATURED_CATEGORIES:
            items = await CatalogService.list_catalog(s, category=category)
            assert len(items) >= MIN_ITEMS_PER_FEATURED_CATEGORY, (
                f"featured tab {category!r} has {len(items)} items "
                f"(< {MIN_ITEMS_PER_FEATURED_CATEGORY})"
            )

    after = await _reconcile_async()
    assert after["drift_count"] == baseline["drift_count"]


async def test_seed_events_non_flat_odds_history() -> None:
    """DEMO-02: each event child carries a NON-flat per-outcome odds history."""
    cfg = SeedConfig(
        n_users=4,
        n_markets=0,
        n_resolved_markets=0,
        n_events=4,
        email_domain="seed-events-odds.demo.xpredict",
    )
    baseline = await _reconcile_async()
    await seed_demo(cfg)

    crypto_slug = _event_slug(_EVENT_TEMPLATES[3], cfg)  # the OPEN Crypto event
    sm = _get_session_maker()
    async with sm() as s:
        group = await CatalogService.get_event(s, crypto_slug)
        assert group is not None
        child = group.markets[0]
        yes_id = next(o.id for o in child.outcomes if o.label.upper() == "YES")
        probabilities = (
            (
                await s.execute(
                    select(OddsSnapshot.probability).where(OddsSnapshot.outcome_id == yes_id)
                )
            )
            .scalars()
            .all()
        )

    assert len(probabilities) >= 2  # history present in every chart window
    assert len(set(probabilities)) > 1  # NON-flat series (DEMO-02)

    after = await _reconcile_async()
    assert after["drift_count"] == baseline["drift_count"]


async def test_seed_demo_guard_blocks_double_seed() -> None:
    """A second seed without --reset is blocked (the demo admin is the marker)."""
    cfg = SeedConfig(
        n_users=2,
        n_markets=2,
        n_resolved_markets=0,
        n_events=0,
        email_domain="seed-guard.demo.xpredict",
    )
    await seed_demo(cfg)
    with pytest.raises(AlreadySeeded):
        await seed_demo(cfg)


async def test_reset_clears_market_groups_and_reseeds() -> None:
    """DEMO-04: --reset wipes ``market_groups`` so the deterministic event slugs re-seed clean."""
    cfg = SeedConfig(
        n_users=4,
        n_markets=0,
        n_resolved_markets=0,
        n_events=4,
        email_domain="seed-events-reset.demo.xpredict",
    )
    await reset_demo()  # clean slate first (global)
    baseline = await _reconcile_async()
    await seed_demo(cfg)

    # The re-seed below recreates the SAME deterministic event slugs; it only succeeds
    # because reset truncates ``market_groups`` (otherwise the UNIQUE slug would collide).
    rc = await main(["--reset"], cfg=cfg)
    assert rc == 0

    sm = _get_session_maker()
    async with sm() as s:
        n_groups = (await s.execute(select(func.count()).select_from(MarketGroup))).scalar_one()
    assert n_groups >= cfg.n_events  # events present after reset + re-seed

    after = await _reconcile_async()
    assert after["drift_count"] == baseline["drift_count"]


async def test_main_reset_wipes_and_repopulates() -> None:
    """``main(["--reset"])`` wipes then re-seeds; demo data is present afterwards."""
    cfg = SeedConfig(
        n_users=2,
        n_markets=2,
        n_resolved_markets=1,
        n_events=0,
        email_domain="seed-main.demo.xpredict",
    )
    await reset_demo()  # clean slate first (global)
    await seed_demo(cfg)

    rc = await main(["--reset"], cfg=cfg)
    assert rc == 0

    sm = _get_session_maker()
    async with sm() as s:
        markets = (await s.execute(select(func.count()).select_from(Market))).scalar_one()
    assert markets > 0
