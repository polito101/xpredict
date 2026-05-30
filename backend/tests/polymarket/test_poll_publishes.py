"""Producer hook #2 (MKT-04): the Polymarket poll publishes ON CHANGE only.

Pitfall 4 / T-09-03: _run_poll_sync must publish an odds-change delta (via its
held AioRedis, post-commit) only for markets whose outcome current_odds actually
changed during sync — and must NOT publish on an unchanged tick.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from app.integrations.polymarket.tasks import _run_poll_sync
from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import Market, Outcome

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


def _gamma_market(source_id: str, slug: str, yes_price: str, no_price: str) -> dict:
    return {
        "id": source_id,
        "question": f"Will {slug} resolve YES?",
        "slug": slug,
        "conditionId": f"cond-{source_id}",
        "outcomes": '["Yes","No"]',
        "outcomePrices": f'["{yes_price}","{no_price}"]',
        "clobTokenIds": '["tok1","tok2"]',
        "volume": "1000000",
        "liquidity": "500000",
        "volume24hr": 50000.0,
        "closed": False,
        "endDate": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
        "description": "Test poll publish market",
    }


async def _seed_pm_market(
    session: AsyncSession,
    source_id: str,
    slug: str,
    yes_odds: str,
) -> Market:
    """Seed an existing POLYMARKET market + YES/NO outcomes at the given odds."""
    market = Market(
        source=MarketSourceEnum.POLYMARKET.value,
        source_market_id=source_id,
        condition_id=f"cond-{source_id}",
        question=f"Will {slug} resolve YES?",
        slug=f"pm-{slug}",
        polymarket_slug=slug,
        resolution_criteria="Resolution via Polymarket UMA oracle",
        status=MarketStatus.OPEN.value,
        deadline=datetime.now(UTC) + timedelta(days=30),
    )
    session.add(market)
    await session.flush()
    no_odds = str(Decimal("1") - Decimal(yes_odds))
    session.add_all(
        [
            Outcome(
                market_id=market.id,
                label="Yes",
                initial_odds=Decimal(yes_odds),
                current_odds=Decimal(yes_odds),
            ),
            Outcome(
                market_id=market.id,
                label="No",
                initial_odds=Decimal(no_odds),
                current_odds=Decimal(no_odds),
            ),
        ]
    )
    await session.flush()
    return market


async def _run_with_gamma(
    session: AsyncSession,
    gamma_markets: list[dict],
) -> AsyncMock:
    """Run _run_poll_sync against the given Gamma response; return the publish mock."""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock()

    mock_client = AsyncMock()
    mock_client.fetch_top_markets = AsyncMock(return_value=gamma_markets)
    mock_client.close = AsyncMock()

    publish_mock = AsyncMock()
    with (
        patch(
            "app.integrations.polymarket.tasks.GammaClient",
            return_value=mock_client,
        ),
        patch(
            "app.integrations.polymarket.tasks.publish_odds_change_async",
            publish_mock,
        ),
    ):
        await _run_poll_sync(redis_override=redis, session_override=session)
    return publish_mock


async def test_poll_publishes_on_actual_change(async_session: AsyncSession) -> None:
    """When a synced YES price differs from stored current_odds, publish the delta."""
    from sqlalchemy import delete

    source_id = "poll-pub-change-001"
    market = await _seed_pm_market(async_session, source_id, "poll-pub-change", "0.5")
    try:
        # Gamma now reports YES 0.6 (changed from the stored 0.5).
        gamma = [_gamma_market(source_id, "poll-pub-change", "0.6", "0.4")]
        publish_mock = await _run_with_gamma(async_session, gamma)

        publish_mock.assert_awaited_once()
        call = publish_mock.call_args
        # Signature: publish_odds_change_async(redis, market_id, deltas)
        published_market_id = call.args[1]
        deltas = call.args[2]
        assert str(published_market_id) == str(market.id)
        odds = {d["odds"] for d in deltas}
        assert "0.600000" in odds  # the changed YES price, as a string
        for d in deltas:
            assert set(d.keys()) == {"outcome_id", "odds"}
            assert isinstance(d["odds"], str)
    finally:
        await async_session.execute(delete(Outcome).where(Outcome.market_id == market.id))
        await async_session.execute(delete(Market).where(Market.id == market.id))
        await async_session.flush()


async def test_poll_does_not_publish_on_unchanged_tick(async_session: AsyncSession) -> None:
    """When the synced price equals the stored current_odds, publish zero times."""
    from sqlalchemy import delete

    source_id = "poll-pub-nochange-001"
    market = await _seed_pm_market(async_session, source_id, "poll-pub-nochange", "0.5")
    try:
        # Gamma reports YES 0.5 — identical to the stored current_odds (no-op tick).
        gamma = [_gamma_market(source_id, "poll-pub-nochange", "0.5", "0.5")]
        publish_mock = await _run_with_gamma(async_session, gamma)

        publish_mock.assert_not_awaited()
    finally:
        await async_session.execute(delete(Outcome).where(Outcome.market_id == market.id))
        await async_session.execute(delete(Market).where(Market.id == market.id))
        await async_session.flush()
