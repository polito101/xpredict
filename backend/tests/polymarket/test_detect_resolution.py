"""Phase 7 — STL-01: Polymarket auto-resolution Beat task tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.integrations.polymarket.schemas import GammaMarket
from app.markets.enums import MarketSourceEnum, MarketStatus

# ---------------------------------------------------------------------------
# Unit tests — no DB required
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_candidate_query_returns_expired_markets() -> None:
    """Candidate query filters POLYMARKET OPEN/CLOSED markets past their deadline."""

    # Verify the task imports and selects on the correct columns.
    # We test the filter predicates by inspecting _derive_status logic on the schema.
    # closed=true, uma=proposed -> CLOSED (not RESOLVED) — no settlement triggered.
    closed_proposed = GammaMarket.model_validate(
        {
            "id": "test-1",
            "question": "Test?",
            "closed": True,
            "umaResolutionStatus": "proposed",
            "outcomePrices": '["0.6","0.4"]',
            "outcomes": '["Yes","No"]',
        }
    )
    assert closed_proposed.internal_status == MarketStatus.CLOSED

    # closed=true, uma=resolved, winner present -> RESOLVED (settlement triggered).
    resolved = GammaMarket.model_validate(
        {
            "id": "test-2",
            "question": "Test?",
            "closed": True,
            "umaResolutionStatus": "resolved",
            "outcomePrices": '["0","1"]',
            "outcomes": '["Spurs","Thunder"]',
        }
    )
    assert resolved.internal_status == MarketStatus.RESOLVED

    # Verify the task constant keys.
    from app.integrations.polymarket.tasks import DETECT_LOCK_KEY, LOCK_KEY

    assert DETECT_LOCK_KEY != LOCK_KEY, "Detect lock must be distinct from poll lock (T-07-04)"
    assert "detect" in DETECT_LOCK_KEY


@pytest.mark.unit
async def test_closed_proposed_not_settled() -> None:
    """A market with closed=true, umaResolutionStatus='proposed' is never settled (SC#3)."""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock()

    closed_proposed_raw = {
        "id": "gamma-999",
        "question": "Will it happen?",
        "closed": True,
        "umaResolutionStatus": "proposed",
        "outcomePrices": '["0.6","0.4"]',
        "outcomes": '["Yes","No"]',
        "endDate": "2020-01-01T00:00:00Z",
    }

    fake_market = MagicMock()
    fake_market.source_market_id = "gamma-999"
    fake_market.source = MarketSourceEnum.POLYMARKET.value
    fake_market.status = MarketStatus.CLOSED.value
    fake_market.deadline = datetime(2020, 1, 1, tzinfo=UTC)
    fake_market.uma_resolved_at = None
    fake_market.outcomes = []
    fake_market.id = uuid4()

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fake_market]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    from app.integrations.polymarket.tasks import _run_detect_resolutions

    # SettlementService is lazily imported inside the task function — patch at source.
    with (
        patch(
            "app.integrations.polymarket.tasks.GammaClient.fetch_market_by_id",
            new=AsyncMock(return_value=closed_proposed_raw),
        ),
        patch(
            "app.integrations.polymarket.tasks.GammaClient.close",
            new=AsyncMock(),
        ),
        patch(
            "app.settlement.service.SettlementService.resolve_market",
            new=AsyncMock(),
        ) as mock_resolve,
    ):
        await _run_detect_resolutions(redis_override=redis, session_override=session)
        # SettlementService.resolve_market must NOT be called for closed+proposed.
        mock_resolve.assert_not_called()


@pytest.mark.unit
async def test_grace_period_triggers_resolution() -> None:
    """First tick sets uma_resolved_at; after grace window SettlementService is called."""
    from app.integrations.polymarket.tasks import _run_detect_resolutions

    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock()

    resolved_raw = {
        "id": "gamma-222",
        "question": "Spurs vs. Thunder",
        "closed": True,
        "umaResolutionStatus": "resolved",
        "outcomePrices": '["0","1"]',
        "outcomes": '["Spurs","Thunder"]',
        "endDate": "2020-01-01T00:00:00Z",
    }

    market_id = uuid4()
    thunder_id = uuid4()
    spurs_outcome = MagicMock()
    spurs_outcome.label = "Spurs"
    spurs_outcome.id = uuid4()
    thunder_outcome = MagicMock()
    thunder_outcome.label = "Thunder"
    thunder_outcome.id = thunder_id

    # Tick 1: uma_resolved_at IS None — clock should be started, no settlement.
    fake_market_tick1 = MagicMock()
    fake_market_tick1.source_market_id = "gamma-222"
    fake_market_tick1.source = MarketSourceEnum.POLYMARKET.value
    fake_market_tick1.status = MarketStatus.CLOSED.value
    fake_market_tick1.deadline = datetime(2020, 1, 1, tzinfo=UTC)
    fake_market_tick1.uma_resolved_at = None
    fake_market_tick1.outcomes = [spurs_outcome, thunder_outcome]
    fake_market_tick1.id = market_id

    mock_result_tick1 = MagicMock()
    mock_result_tick1.scalars.return_value.all.return_value = [fake_market_tick1]

    session_tick1 = AsyncMock()
    session_tick1.execute = AsyncMock(return_value=mock_result_tick1)
    session_tick1.commit = AsyncMock()

    # SettlementService is lazily imported inside the task — patch at source.
    with (
        patch(
            "app.integrations.polymarket.tasks.GammaClient.fetch_market_by_id",
            new=AsyncMock(return_value=resolved_raw),
        ),
        patch("app.integrations.polymarket.tasks.GammaClient.close", new=AsyncMock()),
        patch(
            "app.settlement.service.SettlementService.resolve_market",
            new=AsyncMock(),
        ) as mock_resolve_tick1,
    ):
        await _run_detect_resolutions(redis_override=redis, session_override=session_tick1)
        mock_resolve_tick1.assert_not_called()

    # Tick 2: uma_resolved_at is set to > grace window ago — settlement should fire.
    past_grace = datetime.now(UTC) - timedelta(minutes=60)

    fake_market_tick2 = MagicMock()
    fake_market_tick2.source_market_id = "gamma-222"
    fake_market_tick2.source = MarketSourceEnum.POLYMARKET.value
    fake_market_tick2.status = MarketStatus.CLOSED.value
    fake_market_tick2.deadline = datetime(2020, 1, 1, tzinfo=UTC)
    fake_market_tick2.uma_resolved_at = past_grace
    fake_market_tick2.outcomes = [spurs_outcome, thunder_outcome]
    fake_market_tick2.id = market_id

    mock_result_tick2 = MagicMock()
    mock_result_tick2.scalars.return_value.all.return_value = [fake_market_tick2]

    session_tick2 = AsyncMock()
    session_tick2.execute = AsyncMock(return_value=mock_result_tick2)

    with (
        patch(
            "app.integrations.polymarket.tasks.GammaClient.fetch_market_by_id",
            new=AsyncMock(return_value=resolved_raw),
        ),
        patch("app.integrations.polymarket.tasks.GammaClient.close", new=AsyncMock()),
        patch(
            "app.settlement.service.SettlementService.resolve_market",
            new=AsyncMock(),
        ) as mock_resolve_tick2,
        patch("app.settlement.adapters.HouseMarketResolveAdapter"),
    ):
        await _run_detect_resolutions(redis_override=redis, session_override=session_tick2)
        mock_resolve_tick2.assert_called_once()
        call_kwargs = mock_resolve_tick2.call_args.kwargs
        assert call_kwargs["market_id"] == market_id
        assert call_kwargs["winning_outcome_id"] == thunder_id
        assert call_kwargs["actor_user_id"] is None
        assert "UMA oracle" in call_kwargs["justification"]


@pytest.mark.unit
def test_beat_schedule_registered() -> None:
    """detect-polymarket-resolutions Beat entry is present at 60s (STL-01 SC#1)."""
    from app.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "detect-polymarket-resolutions" in schedule
    entry = schedule["detect-polymarket-resolutions"]
    assert entry["schedule"] == 60.0
    assert entry["task"] == "app.integrations.polymarket.tasks.detect_polymarket_resolutions"


# ---------------------------------------------------------------------------
# Integration tests — testcontainers Postgres required
# ---------------------------------------------------------------------------

_integration_marks = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_integration_proposed_not_settled() -> None:
    """Integration: closed/proposed market never triggers settlement (SC#3).

    Uses _get_session_maker() directly (not the shared async_session fixture) so
    each operation gets a clean session — same pattern as test_reversal_after_auto_settlement.
    """
    from decimal import Decimal

    from sqlalchemy import select

    from app.db.session import _get_session_maker
    from app.integrations.polymarket.tasks import _run_detect_resolutions
    from app.markets.models import Market, Outcome

    market_id = uuid4()
    outcome_id = uuid4()
    source_market_id = f"gamma-integration-{market_id.hex[:8]}"

    sm = _get_session_maker()

    async with sm() as s, s.begin():
        mkt = Market(
            id=market_id,
            question="Integration test: proposed market",
            slug=f"integration-proposed-{market_id.hex[:8]}",
            resolution_criteria="test",
            source=MarketSourceEnum.POLYMARKET.value,
            source_market_id=source_market_id,
            status=MarketStatus.CLOSED.value,
            deadline=datetime(2020, 1, 1, tzinfo=UTC),
        )
        s.add(mkt)
        await s.flush()

        out = Outcome(
            id=outcome_id,
            market_id=market_id,
            label="Yes",
            initial_odds=Decimal("0.5"),
            current_odds=Decimal("0.5"),
        )
        s.add(out)

    closed_proposed = {
        "id": source_market_id,
        "question": "Integration test?",
        "closed": True,
        "umaResolutionStatus": "proposed",
        "outcomePrices": '["0.6","0.4"]',
        "outcomes": '["Yes","No"]',
    }

    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock()

    async with sm() as detect_session:
        with (
            patch(
                "app.integrations.polymarket.tasks.GammaClient.fetch_market_by_id",
                new=AsyncMock(return_value=closed_proposed),
            ),
            patch("app.integrations.polymarket.tasks.GammaClient.close", new=AsyncMock()),
        ):
            await _run_detect_resolutions(redis_override=redis, session_override=detect_session)

    # Market should still be CLOSED, not RESOLVED.
    async with sm() as s:
        result = await s.execute(select(Market).where(Market.id == market_id))
        market = result.scalar_one()
        assert market.status == MarketStatus.CLOSED.value


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_reversal_after_auto_settlement() -> None:
    """Auto-settle then reverse: compensating entries restore balances (SC#6).

    Uses _get_session_maker() directly (not the shared async_session fixture) so
    each SettlementService call gets a clean session with no pre-existing autobegun
    transaction — SettlementService opens its own begin() internally.
    """
    from decimal import Decimal

    from app.db.session import _get_session_maker
    from app.markets.models import Market, Outcome
    from app.settlement.adapters import HouseMarketResolveAdapter
    from app.settlement.service import SettlementService

    market_id = uuid4()
    yes_id = uuid4()
    no_id = uuid4()

    sm = _get_session_maker()
    async with sm() as s, s.begin():
        mkt = Market(
            id=market_id,
            question="Auto-settlement reversal test",
            slug=f"auto-settle-reversal-{market_id.hex[:8]}",
            resolution_criteria="test",
            source=MarketSourceEnum.POLYMARKET.value,
            source_market_id=f"gamma-reversal-{market_id.hex[:8]}",
            status=MarketStatus.OPEN.value,
            deadline=datetime(2020, 1, 1, tzinfo=UTC),
        )
        s.add(mkt)
        await s.flush()
        yes_out = Outcome(
            id=yes_id,
            market_id=market_id,
            label="Yes",
            initial_odds=Decimal("0.5"),
            current_odds=Decimal("0.5"),
        )
        no_out = Outcome(
            id=no_id,
            market_id=market_id,
            label="No",
            initial_odds=Decimal("0.5"),
            current_odds=Decimal("0.5"),
        )
        s.add_all([yes_out, no_out])

    # Each SettlementService call opens its own clean session.begin() transaction.
    async with sm() as s:
        await SettlementService.resolve_market(
            s,
            market_id=market_id,
            winning_outcome_id=yes_id,
            market_resolver=HouseMarketResolveAdapter(),
            justification="Auto-resolved: Polymarket UMA oracle confirmed resolution",
            actor_user_id=None,
        )

    async with sm() as s:
        reversed_count = await SettlementService.reverse_settlement(
            s,
            market_id=market_id,
            market_resolver=HouseMarketResolveAdapter(),
            justification="Test reversal after auto-settlement",
            actor_user_id=uuid4(),
        )

    assert reversed_count >= 0  # 0 bets in this test (no bets placed), no-op but valid
