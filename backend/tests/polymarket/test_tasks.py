"""Tests for Polymarket Celery tasks — poll lock, upsert, snapshot, beat schedule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.integrations.polymarket.tasks import (
    EVENTS_LOCK_KEY,
    LOCK_KEY,
    _run_poll_events,
    _run_poll_sync,
    _run_snapshot_odds,
    acquire_events_lock,
    acquire_poll_lock,
    release_poll_lock,
)
from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import Market, OddsSnapshot, Outcome, generate_slug

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Unit tests — mock Redis, no DB
# ---------------------------------------------------------------------------
pytestmark_unit = [pytest.mark.unit]


@pytest.mark.unit
async def test_acquire_poll_lock_calls_setnx() -> None:
    """acquire_poll_lock uses SETNX with TTL and returns an ownership token (WR-05)."""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    result = await acquire_poll_lock(redis)

    # A non-empty token string is returned on success (no longer a bool).
    assert isinstance(result, str) and result
    redis.set.assert_called_once()
    call = redis.set.call_args
    assert call.kwargs.get("nx") is True or call[1].get("nx") is True
    # The lock VALUE is the unique token, not a constant "1".
    assert call.args[1] == result


@pytest.mark.unit
async def test_acquire_poll_lock_returns_none_when_held() -> None:
    """When SETNX fails (lock held), acquire returns None (WR-05)."""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=None)

    assert await acquire_poll_lock(redis) is None


@pytest.mark.unit
async def test_release_poll_lock_compare_and_deletes(monkeypatch: pytest.MonkeyPatch) -> None:
    """release_poll_lock uses a compare-and-delete eval keyed on the owning token (WR-05)."""
    redis = AsyncMock()
    redis.eval = AsyncMock()

    await release_poll_lock(redis, "tok-123")

    # Owner-checked release: eval(script, numkeys=1, LOCK_KEY, token).
    redis.eval.assert_called_once()
    call = redis.eval.call_args
    assert call.args[1] == 1
    assert call.args[2] == LOCK_KEY
    assert call.args[3] == "tok-123"


@pytest.mark.unit
async def test_poll_skipped_when_lock_held() -> None:
    """When lock is held, GammaClient.fetch_top_markets is NOT called."""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=False)  # lock NOT acquired

    with patch(
        "app.integrations.polymarket.tasks.GammaClient",
    ) as mock_client_cls:
        await _run_poll_sync(redis_override=redis)
        mock_client_cls.assert_not_called()


@pytest.mark.unit
async def test_poll_acquires_and_releases_lock() -> None:
    """Poll acquires lock before sync and releases after (owner-checked — WR-05)."""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.eval = AsyncMock()
    redis.aclose = AsyncMock()

    mock_client = AsyncMock()
    mock_client.fetch_top_markets = AsyncMock(return_value=[])
    mock_client.close = AsyncMock()

    with (
        patch(
            "app.integrations.polymarket.tasks.GammaClient",
            return_value=mock_client,
        ),
        patch(
            "app.integrations.polymarket.tasks.PolymarketAdapter",
        ) as mock_adapter_cls,
    ):
        mock_adapter = AsyncMock()
        mock_adapter.sync_top25 = AsyncMock(return_value=0)
        mock_adapter_cls.return_value = mock_adapter

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.close = AsyncMock()

        await _run_poll_sync(
            redis_override=redis,
            session_override=mock_session,
        )

    # Lock was acquired (set with nx=True)
    redis.set.assert_called_once()
    # Lock was released via the owner-checked compare-and-delete eval (WR-05).
    redis.eval.assert_called_once()
    assert redis.eval.call_args.args[2] == LOCK_KEY


@pytest.mark.unit
def test_beat_schedule_entries() -> None:
    """Beat schedule fires the curated events poll @300s, NOT the dropped top-25 poll.

    Phase 14 swapped ``poll-polymarket-top25`` @30s out of the schedule for
    ``poll-polymarket-events`` @300s; ``snapshot-odds`` @300s and
    ``detect-polymarket-resolutions`` @60s are untouched (the assertions for the
    dropped task INVERTED after the swap — SC#1).
    """
    from app.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule

    # The top-25 poll is dropped from the schedule (the task stays importable).
    assert "poll-polymarket-top25" not in schedule

    # The curated per-category events poll fires @300s.
    assert "poll-polymarket-events" in schedule
    assert schedule["poll-polymarket-events"]["schedule"] == 300.0
    assert (
        schedule["poll-polymarket-events"]["task"]
        == "app.integrations.polymarket.tasks.poll_polymarket_events"
    )

    # Untouched neighbours.
    assert "snapshot-odds" in schedule
    assert schedule["snapshot-odds"]["schedule"] == 300.0
    assert schedule["snapshot-odds"]["task"] == "app.integrations.polymarket.tasks.snapshot_odds"
    assert "detect-polymarket-resolutions" in schedule
    assert schedule["detect-polymarket-resolutions"]["schedule"] == 60.0


# ---------------------------------------------------------------------------
# Unit tests — curated events poll (mock Redis + GammaClient, no DB)
# ---------------------------------------------------------------------------


def _event_payload(event_id: str, *, volume24hr: float, condition_id: str) -> dict[str, object]:
    """Minimal Gamma ``/events`` element that parses + (optionally) clears the floor.

    Event-level ``volume24hr`` is a raw FLOAT (Pitfall 1) — drives the
    ``volume_24hr_decimal`` floor check. One child market with a ``conditionId``
    so ``sync_events`` sees a real child.
    """
    return {
        "id": event_id,
        "slug": f"evt-{event_id}",
        "title": f"Event {event_id}",
        "closed": False,
        "volume24hr": volume24hr,
        "volume": volume24hr,
        "tags": [{"id": "2", "label": "Politics", "slug": "politics"}],
        "markets": [
            {
                "id": f"mkt-{event_id}",
                "question": f"Will event {event_id} resolve?",
                "conditionId": condition_id,
                "outcomes": '["Yes","No"]',
                "outcomePrices": '["0.6","0.4"]',
                "clobTokenIds": '["t1","t2"]',
                "volume": "100000",
                "groupItemTitle": "",
                "closed": False,
            }
        ],
    }


@pytest.mark.unit
async def test_acquire_events_lock_uses_distinct_key() -> None:
    """The events lock SETNX targets EVENTS_LOCK_KEY, never the poll LOCK_KEY (T-14-13)."""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    token = await acquire_events_lock(redis)

    assert isinstance(token, str) and token
    redis.set.assert_called_once()
    call = redis.set.call_args
    # SETNX on the DISTINCT events key — not the poll lock key.
    assert call.args[0] == EVENTS_LOCK_KEY
    assert call.args[0] != LOCK_KEY
    assert call.kwargs.get("nx") is True or call[1].get("nx") is True
    # The lock VALUE is the returned ownership token.
    assert call.args[1] == token


@pytest.mark.unit
async def test_poll_events_skipped_when_lock_held() -> None:
    """When the events lock is held, GammaClient is NOT constructed (no fetch)."""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=False)  # lock NOT acquired
    redis.eval = AsyncMock()
    redis.aclose = AsyncMock()

    with patch("app.integrations.polymarket.tasks.GammaClient") as mock_client_cls:
        await _run_poll_events(redis_override=redis)
        mock_client_cls.assert_not_called()


@pytest.mark.unit
async def test_poll_events_keeps_last_good_per_category() -> None:
    """One category's fetch raising must NOT abort the others (CAT-05 / T-14-12).

    Politics (tag_id="2") raises a NetworkError; Sports (tag_id="1") returns a
    floor-clearing event. The loop must continue: ``sync_events`` is reached for
    Sports and ``session.rollback`` is called for the failing Politics category.
    """
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.eval = AsyncMock()
    redis.aclose = AsyncMock()

    sports_event = _event_payload("evt-sports", volume24hr=50_000.0, condition_id="cond-sports")

    async def fake_fetch(
        *, tag_id: str, limit: int = 10, offset: int = 0
    ) -> list[dict[str, object]]:
        if tag_id == "2":  # Politics — highest priority, fails
            raise httpx.NetworkError("boom")
        if tag_id == "1":  # Sports — next priority, succeeds with a floor-clearing event
            return [sports_event]
        return []  # remaining categories: empty page

    mock_client = AsyncMock()
    mock_client.fetch_events = AsyncMock(side_effect=fake_fetch)
    mock_client.close = AsyncMock()

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()

    with (
        patch("app.integrations.polymarket.tasks.GammaClient", return_value=mock_client),
        patch("app.integrations.polymarket.tasks.PolymarketAdapter") as mock_adapter_cls,
    ):
        mock_adapter = AsyncMock()
        mock_adapter.sync_events = AsyncMock(return_value=1)
        mock_adapter.changed_markets = []
        mock_adapter_cls.return_value = mock_adapter

        await _run_poll_events(redis_override=redis, session_override=mock_session)

    # The loop did NOT abort on Politics: Sports still synced (keep-last-good).
    assert mock_adapter.sync_events.await_count == 1
    sync_call = mock_adapter.sync_events.await_args
    assert sync_call.kwargs["category"] == "Sports"
    # The failing Politics category was rolled back (not committed).
    assert mock_session.rollback.await_count >= 1
    # Exactly one category committed (Sports); the failing one did not commit.
    assert mock_session.commit.await_count == 1
    # The lock was released via the owner-checked eval on the EVENTS key (WR-05).
    redis.eval.assert_called_once()
    assert redis.eval.call_args.args[2] == EVENTS_LOCK_KEY


@pytest.mark.unit
async def test_poll_events_publishes_per_category_not_cumulative() -> None:
    """Each category publishes ONLY its own deltas, not the cumulative run (14-REVIEW CR-02).

    One adapter instance is reused across all categories. Here ``sync_events`` has a
    side_effect that APPENDS exactly one delta to ``adapter.changed_markets`` per
    call (mirroring the real append-only accumulator), with the list starting at
    ``[]``. Two categories (Politics tag_id="2", Sports tag_id="1") return a
    floor-clearing event; the rest return empty. Under the CR-02 fix the loop resets
    ``adapter.changed_markets = []`` before each ``sync_events``, so the per-category
    publish sees ONLY that category's single delta → ``publish_odds_change_async`` is
    awaited exactly twice total (once per category), and no delta is published twice.
    Under the reverted (no-reset) code the accumulator would carry Politics' delta into
    Sports' publish loop → 1 + 2 = 3 awaits, re-publishing Politics' delta.
    """
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.eval = AsyncMock()
    redis.aclose = AsyncMock()

    politics_event = _event_payload("evt-politics", volume24hr=50_000.0, condition_id="cond-pol")
    sports_event = _event_payload("evt-sports", volume24hr=50_000.0, condition_id="cond-spo")

    async def fake_fetch(
        *, tag_id: str, limit: int = 10, offset: int = 0
    ) -> list[dict[str, object]]:
        if tag_id == "2":  # Politics — floor-clearing event
            return [politics_event]
        if tag_id == "1":  # Sports — floor-clearing event
            return [sports_event]
        return []  # every other category: empty page

    mock_client = AsyncMock()
    mock_client.fetch_events = AsyncMock(side_effect=fake_fetch)
    mock_client.close = AsyncMock()

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()

    publish_mock = AsyncMock()

    with (
        patch("app.integrations.polymarket.tasks.GammaClient", return_value=mock_client),
        patch("app.integrations.polymarket.tasks.PolymarketAdapter") as mock_adapter_cls,
        patch("app.integrations.polymarket.tasks.publish_odds_change_async", publish_mock),
    ):
        mock_adapter = AsyncMock()
        # Append-only accumulator, starting empty — exactly like the real adapter.
        mock_adapter.changed_markets = []
        # Per-call counter gives each category a UNIQUE delta so we can prove no
        # single delta is published twice.
        call_state = {"n": 0}

        async def fake_sync_events(session: object, curated: object, *, category: str) -> int:
            call_state["n"] += 1
            mock_adapter.changed_markets.append(
                (f"market-{category}-{call_state['n']}", [{"outcome_id": "o1", "odds": "0.6"}]),
            )
            return 1

        mock_adapter.sync_events = AsyncMock(side_effect=fake_sync_events)
        mock_adapter_cls.return_value = mock_adapter

        await _run_poll_events(redis_override=redis, session_override=mock_session)

    # Two categories synced (Politics + Sports) — sanity on the setup.
    assert mock_adapter.sync_events.await_count == 2
    synced_categories = [c.kwargs["category"] for c in mock_adapter.sync_events.await_args_list]
    assert synced_categories == ["Politics", "Sports"]

    # CR-02 core: total publishes == number of categories synced (one delta each),
    # NOT the cumulative 1 + 2 = 3 the un-reset accumulator would produce.
    assert publish_mock.await_count == 2

    # No single delta (market_id) is published twice — each publish is a distinct market.
    published_market_ids = [call.args[1] for call in publish_mock.await_args_list]
    assert len(published_market_ids) == len(set(published_market_ids))
    assert set(published_market_ids) == {"market-Politics-1", "market-Sports-2"}


@pytest.mark.unit
async def test_poll_events_dedup_before_floor() -> None:
    """A duplicate event id across categories is skipped — first-by-priority (CAT-02).

    Both Politics (tag_id="2") and Sports (tag_id="1") return the SAME event id;
    the second occurrence is dropped by the cycle-level ``seen_event_ids`` set, so
    ``sync_events`` is called for Politics but the event is NOT re-synced for
    Sports (Pitfall 4).
    """
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.eval = AsyncMock()
    redis.aclose = AsyncMock()

    shared = _event_payload("evt-shared", volume24hr=50_000.0, condition_id="cond-shared")

    async def fake_fetch(
        *, tag_id: str, limit: int = 10, offset: int = 0
    ) -> list[dict[str, object]]:
        if tag_id in ("2", "1"):  # Politics AND Sports surface the same event
            return [shared]
        return []

    mock_client = AsyncMock()
    mock_client.fetch_events = AsyncMock(side_effect=fake_fetch)
    mock_client.close = AsyncMock()

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()

    with (
        patch("app.integrations.polymarket.tasks.GammaClient", return_value=mock_client),
        patch("app.integrations.polymarket.tasks.PolymarketAdapter") as mock_adapter_cls,
    ):
        mock_adapter = AsyncMock()
        mock_adapter.sync_events = AsyncMock(return_value=1)
        mock_adapter.changed_markets = []
        mock_adapter_cls.return_value = mock_adapter

        await _run_poll_events(redis_override=redis, session_override=mock_session)

    # The event synced exactly once — under Politics (higher priority), not Sports.
    assert mock_adapter.sync_events.await_count == 1
    assert mock_adapter.sync_events.await_args.kwargs["category"] == "Politics"


# ---------------------------------------------------------------------------
# Integration tests — testcontainers Postgres
# ---------------------------------------------------------------------------

_integration_marks = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_poll_upserts_markets(async_session: AsyncSession) -> None:
    """Polling with mocked GammaClient creates markets in DB via adapter."""
    from sqlalchemy import delete, select

    sample_markets = [
        {
            "id": "test-poll-001",
            "question": "Will poll test market 1 resolve?",
            "slug": "poll-test-1",
            "conditionId": "cond-001",
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.65","0.35"]',
            "clobTokenIds": '["tok1","tok2"]',
            "volume": "1000000",
            "liquidity": "500000",
            "volume24hr": 50000.0,
            "closed": False,
            "endDate": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
            "description": "Test poll market 1",
        },
        {
            "id": "test-poll-002",
            "question": "Will poll test market 2 resolve?",
            "slug": "poll-test-2",
            "conditionId": "cond-002",
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.40","0.60"]',
            "clobTokenIds": '["tok3","tok4"]',
            "volume": "2000000",
            "liquidity": "800000",
            "volume24hr": 80000.0,
            "closed": False,
            "endDate": (datetime.now(UTC) + timedelta(days=15)).isoformat(),
            "description": "Test poll market 2",
        },
    ]

    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock()

    mock_client = AsyncMock()
    mock_client.fetch_top_markets = AsyncMock(return_value=sample_markets)
    mock_client.close = AsyncMock()

    with patch(
        "app.integrations.polymarket.tasks.GammaClient",
        return_value=mock_client,
    ):
        await _run_poll_sync(
            redis_override=redis,
            session_override=async_session,
        )

    # Verify markets were upserted
    result = await async_session.execute(
        select(Market).where(
            Market.source == MarketSourceEnum.POLYMARKET.value,
            Market.source_market_id.in_(["test-poll-001", "test-poll-002"]),
        ),
    )
    markets = list(result.scalars().all())
    assert len(markets) == 2

    # Clean up
    for m in markets:
        await async_session.execute(
            delete(Outcome).where(Outcome.market_id == m.id),
        )
        await async_session.execute(
            delete(Market).where(Market.id == m.id),
        )
    await async_session.flush()


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_snapshot_odds_writes_rows(async_session: AsyncSession) -> None:
    """Snapshot task writes OddsSnapshot rows for open markets."""
    from sqlalchemy import delete, select

    # Create a market with 2 outcomes
    market = Market(
        question="Snapshot test market?",
        slug=generate_slug("Snapshot test market?"),
        resolution_criteria="Test criteria",
        source=MarketSourceEnum.HOUSE.value,
        status=MarketStatus.OPEN.value,
        deadline=datetime.now(UTC) + timedelta(days=1),
    )
    async_session.add(market)
    await async_session.flush()

    yes = Outcome(
        market_id=market.id,
        label="YES",
        initial_odds=Decimal("0.600000"),
        current_odds=Decimal("0.600000"),
    )
    no = Outcome(
        market_id=market.id,
        label="NO",
        initial_odds=Decimal("0.400000"),
        current_odds=Decimal("0.400000"),
    )
    async_session.add_all([yes, no])
    await async_session.flush()

    # Run snapshot
    await _run_snapshot_odds(session_override=async_session)

    # Verify snapshots were created
    result = await async_session.execute(
        select(OddsSnapshot).where(OddsSnapshot.market_id == market.id),
    )
    snapshots = list(result.scalars().all())
    assert len(snapshots) == 2

    # Verify probabilities match current_odds
    snap_probs = sorted([s.probability for s in snapshots])
    assert snap_probs == sorted([Decimal("0.400000"), Decimal("0.600000")])

    # Clean up
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
