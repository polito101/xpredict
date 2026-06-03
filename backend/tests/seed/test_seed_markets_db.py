"""Bloque 2 — DB-backed house-market seeding (admin + OPEN markets via service).

Markets are created through ``MarketService.create_market`` (never a hand-written
INSERT), committed so the bet read-adapter (own-connection reads) sees them. Each
test asserts against the ids ``seed_markets`` returns (scoped, collision-free in
the shared session-scoped container) and namespaces its demo admin by email.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from app.auth.models import User
from app.db.session import _get_session_maker
from app.markets.models import Market, Outcome
from bin.seed_demo import SeedConfig, build_market_specs, seed_markets

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine:
    return engine


async def _get_market(market_id: UUID) -> Market | None:
    sm = _get_session_maker()
    async with sm() as s:
        return (await s.execute(select(Market).where(Market.id == market_id))).scalar_one_or_none()


async def _outcomes(market_id: UUID) -> list[Outcome]:
    sm = _get_session_maker()
    async with sm() as s:
        return list(
            (await s.execute(select(Outcome).where(Outcome.market_id == market_id))).scalars().all()
        )


async def _admin_by_email(email: str) -> User | None:
    sm = _get_session_maker()
    async with sm() as s:
        return (
            await s.execute(select(User).where(User.email == email))  # type: ignore[arg-type]
        ).scalar_one_or_none()


async def test_seed_markets_creates_open_house_markets_with_outcomes() -> None:
    """Each seeded market is committed OPEN/HOUSE with a future deadline and YES/NO
    outcomes whose YES odds equal the spec — and SeededMarket exposes the ids."""
    cfg = SeedConfig(n_markets=4, n_resolved_markets=1, email_domain="seed-markets.demo.xpredict")
    specs = build_market_specs(cfg)

    seeded = await seed_markets(cfg)

    assert len(seeded) == 4
    now = datetime.now(UTC)
    for sm_market, spec in zip(seeded, specs, strict=True):
        market = await _get_market(sm_market.id)
        assert market is not None
        assert market.status == "OPEN"
        assert market.source == "HOUSE"
        assert market.question == spec.question
        assert market.category == spec.category
        assert market.deadline > now  # future deadline (place_bet is_open requires it)

        outcomes = await _outcomes(sm_market.id)
        assert {o.label for o in outcomes} == {"YES", "NO"}
        yes = next(o for o in outcomes if o.label == "YES")
        assert yes.current_odds == spec.initial_odds_yes
        # SeededMarket carries the YES/NO ids + the resolve flag for later blocks.
        assert sm_market.yes_outcome_id == yes.id
        assert sm_market.initial_odds_yes == spec.initial_odds_yes
        assert sm_market.resolve_to == spec.resolve_to


async def test_seed_markets_creates_superuser_admin() -> None:
    """The demo admin (namespaced by domain) is a verified superuser."""
    cfg = SeedConfig(n_markets=2, n_resolved_markets=0, email_domain="seed-admin.demo.xpredict")

    await seed_markets(cfg)

    admin = await _admin_by_email(f"demo-admin@{cfg.email_domain}")
    assert admin is not None
    assert admin.is_superuser is True
    assert admin.is_verified is True
