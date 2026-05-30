from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.auth.models import User
    from app.markets.models import Market


@pytest.fixture(autouse=True)
def _reset_rate_limit_storage():
    from app.auth.rate_limit import limiter

    try:
        limiter._limiter.reset()
    except Exception:
        with contextlib.suppress(Exception):
            limiter._storage.reset()
    yield


@pytest_asyncio.fixture(loop_scope="session")
async def admin_user(async_session: AsyncSession) -> AsyncGenerator[User, None]:
    from sqlalchemy import delete

    from app.auth.models import User

    user = User(
        email="market-admin@test.com",
        hashed_password="not-a-real-hash",
        is_active=True,
        is_superuser=True,
        is_verified=True,
        display_name="Market Admin",
    )
    async_session.add(user)
    await async_session.flush()
    try:
        yield user
    finally:
        await async_session.execute(delete(User).where(User.id == user.id))
        await async_session.flush()


@pytest_asyncio.fixture(loop_scope="session")
async def sample_market(async_session: AsyncSession) -> AsyncGenerator[Market, None]:
    from sqlalchemy import delete

    from app.markets.enums import MarketSourceEnum, MarketStatus
    from app.markets.models import Market, OddsSnapshot, Outcome, generate_slug

    market = Market(
        question="Will it rain tomorrow?",
        slug=generate_slug("Will it rain tomorrow?"),
        resolution_criteria="Rain recorded at station X by 23:59 UTC",
        category="weather",
        source=MarketSourceEnum.HOUSE.value,
        status=MarketStatus.OPEN.value,
        deadline=datetime.now(UTC) + timedelta(days=1),
    )
    async_session.add(market)
    await async_session.flush()

    yes = Outcome(
        market_id=market.id,
        label="YES",
        initial_odds=Decimal("0.500000"),
        current_odds=Decimal("0.500000"),
    )
    no = Outcome(
        market_id=market.id,
        label="NO",
        initial_odds=Decimal("0.500000"),
        current_odds=Decimal("0.500000"),
    )
    async_session.add_all([yes, no])
    await async_session.flush()

    snap_yes = OddsSnapshot(
        market_id=market.id,
        outcome_id=yes.id,
        probability=Decimal("0.500000"),
    )
    snap_no = OddsSnapshot(
        market_id=market.id,
        outcome_id=no.id,
        probability=Decimal("0.500000"),
    )
    async_session.add_all([snap_yes, snap_no])
    await async_session.flush()

    try:
        yield market
    finally:
        await async_session.execute(
            delete(OddsSnapshot).where(OddsSnapshot.market_id == market.id),
        )
        await async_session.execute(
            delete(Outcome).where(Outcome.market_id == market.id),
        )
        await async_session.execute(
            delete(Market).where(Market.id == market.id),
        )
        await async_session.flush()


@pytest_asyncio.fixture(loop_scope="session")
async def market_with_bets(
    async_session: AsyncSession,
    sample_market: Market,
) -> AsyncGenerator[Market, None]:
    from sqlalchemy import update

    from app.markets.models import Market

    await async_session.execute(
        update(Market).where(Market.id == sample_market.id).values(bet_count=1),
    )
    await async_session.flush()
    await async_session.refresh(sample_market)
    try:
        yield sample_market
    finally:
        await async_session.execute(
            update(Market).where(Market.id == sample_market.id).values(bet_count=0),
        )
        await async_session.flush()
