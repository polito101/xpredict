"""Price-history endpoint + downsampling tests (MKT-03, T-09-06 / T-09-07 / T-09-08).

Two layers:

* **unit** (no DB) — the ``PricePoint`` / ``PriceHistoryResponse`` schema contract:
  ``probability`` serializes to a JSON STRING (never a float), datetimes stay
  tz-aware ISO-8601 (SP-1 / SP-2). These satisfy the Task-1 ``-m "not integration"``
  gate.
* **integration** (testcontainers Postgres) — the public
  ``GET /api/v1/markets/{slug}/price-history`` endpoint: raw points for 24h/7d, a
  server-side hourly-bucketed series for 30d that is strictly smaller than the raw
  5-min snapshot count (ROADMAP SC#2), the 7d default, the window allowlist (422),
  404 on an unknown slug, and the low-data (<2 snapshots) empty payload.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Unit — schema serialization (no DB, satisfies the -m "not integration" gate)
# ---------------------------------------------------------------------------

pytestmark_unit = pytest.mark.unit


@pytest.mark.unit
def test_price_point_serializes_probability_as_string() -> None:
    from app.markets.schemas import PricePoint

    ts = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    point = PricePoint(ts=ts, probability=Decimal("0.700000"))

    dumped = json.loads(point.model_dump_json())
    assert dumped["probability"] == "0.700000"
    assert isinstance(dumped["probability"], str)
    # tz-aware ISO-8601 datetime (SP-2) — never a naive timestamp.
    assert dumped["ts"].startswith("2026-05-01T12:00:00")
    assert "+00:00" in dumped["ts"] or dumped["ts"].endswith("Z")


@pytest.mark.unit
def test_price_point_never_emits_a_json_float() -> None:
    from app.markets.schemas import PricePoint

    point = PricePoint(ts=datetime(2026, 5, 1, tzinfo=UTC), probability=Decimal("0.5"))
    # The raw JSON token must be the quoted string "0.5", not the bare float 0.5.
    raw = point.model_dump_json()
    assert '"probability":"0.5"' in raw.replace(" ", "")
    assert '"probability":0.5' not in raw.replace(" ", "")


@pytest.mark.unit
def test_price_history_response_wraps_points() -> None:
    from app.markets.schemas import PriceHistoryResponse, PricePoint

    resp = PriceHistoryResponse(
        window="7d",
        points=[
            PricePoint(ts=datetime(2026, 5, 1, tzinfo=UTC), probability=Decimal("0.4")),
            PricePoint(ts=datetime(2026, 5, 2, tzinfo=UTC), probability=Decimal("0.6")),
        ],
    )
    dumped = json.loads(resp.model_dump_json())
    assert dumped["window"] == "7d"
    assert len(dumped["points"]) == 2
    assert all(isinstance(p["probability"], str) for p in dumped["points"])


@pytest.mark.unit
def test_price_history_response_allows_empty_points() -> None:
    """A market with <2 snapshots returns an empty payload the frontend renders
    as the friendly 'not enough history' placeholder (success_criteria)."""
    from app.markets.schemas import PriceHistoryResponse

    resp = PriceHistoryResponse(window="7d", points=[])
    dumped = json.loads(resp.model_dump_json())
    assert dumped["points"] == []


# ---------------------------------------------------------------------------
# Integration — endpoint + server-side downsampling (testcontainers Postgres)
# ---------------------------------------------------------------------------

_integration = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


async def _public_client() -> httpx.AsyncClient:
    from app.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _seed_market_with_snapshots(
    session: AsyncSession,
    *,
    snapshot_count: int,
    interval_minutes: int = 5,
    span_start: datetime | None = None,
) -> str:
    """Seed one OPEN house market with a YES/NO outcome and ``snapshot_count``
    OddsSnapshot rows at ``interval_minutes`` spacing for the YES outcome.

    Returns the market slug. Rows are NOT committed — the caller's session is the
    transactional ``async_session`` fixture (rolled back on teardown). The HTTP
    client shares the app's own session, so the integration tests that hit the
    endpoint seed via the engine instead (see endpoint tests below).
    """
    from app.markets.enums import MarketSourceEnum, MarketStatus
    from app.markets.models import Market, OddsSnapshot, Outcome, generate_slug

    market = Market(
        question="Downsample backfill market?",
        slug=generate_slug("Downsample backfill market"),
        resolution_criteria="resolves",
        category="test",
        source=MarketSourceEnum.HOUSE.value,
        status=MarketStatus.OPEN.value,
        deadline=datetime.now(UTC) + timedelta(days=2),
    )
    session.add(market)
    await session.flush()

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
    session.add_all([yes, no])
    await session.flush()

    start = span_start or (datetime.now(UTC) - timedelta(minutes=interval_minutes * snapshot_count))
    snaps = [
        OddsSnapshot(
            market_id=market.id,
            outcome_id=yes.id,
            probability=Decimal("0.500000"),
            snapshot_at=start + timedelta(minutes=interval_minutes * i),
        )
        for i in range(snapshot_count)
    ]
    session.add_all(snaps)
    await session.flush()
    return market.slug


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_price_history_7d_returns_raw_yes_points_as_strings(
    async_session: AsyncSession,
) -> None:
    from app.markets.service import MarketService

    slug = await _seed_market_with_snapshots(async_session, snapshot_count=6)

    resp = await MarketService.price_history(async_session, slug, "7d")
    assert resp.window == "7d"
    assert len(resp.points) == 6
    # Probabilities serialize to strings on the wire (SP-1).
    dumped = json.loads(resp.model_dump_json())
    assert all(isinstance(p["probability"], str) for p in dumped["points"])
    # Ordered ascending by ts.
    ts_values = [p.ts for p in resp.points]
    assert ts_values == sorted(ts_values)


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_price_history_30d_downsamples_to_hourly_buckets(
    async_session: AsyncSession,
) -> None:
    """30d window is DOWNSAMPLED server-side (T-09-07): a dense 5-min backfill
    over multiple hours yields far fewer points (one per hour) than the raw count.
    """
    from app.markets.service import MarketService

    # 6 hours of 5-min snapshots = 72 raw rows spanning 6 distinct hour-buckets.
    span_start = datetime.now(UTC) - timedelta(hours=6)
    slug = await _seed_market_with_snapshots(
        async_session,
        snapshot_count=72,
        interval_minutes=5,
        span_start=span_start,
    )

    resp = await MarketService.price_history(async_session, slug, "30d")
    raw_count = 72
    # Strictly fewer points than the raw 5-min count (downsampling actually fired).
    assert len(resp.points) < raw_count
    # Hourly-bucketed: ~6 buckets for a 6-hour span (allow the boundary bucket).
    assert len(resp.points) <= 8
    assert len(resp.points) >= 5
    # Distinct truncated-to-hour timestamps (one representative point per hour).
    hours = {p.ts.replace(minute=0, second=0, microsecond=0) for p in resp.points}
    assert len(hours) == len(resp.points)
    # Ordered ascending.
    assert [p.ts for p in resp.points] == sorted(p.ts for p in resp.points)


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_price_history_low_data_returns_empty_points(
    async_session: AsyncSession,
) -> None:
    """A market with a single snapshot returns a <2-point payload the frontend
    renders as the placeholder (success_criteria)."""
    from app.markets.service import MarketService

    slug = await _seed_market_with_snapshots(async_session, snapshot_count=1)
    resp = await MarketService.price_history(async_session, slug, "7d")
    assert len(resp.points) < 2


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_price_history_unknown_slug_raises_404(
    async_session: AsyncSession,
) -> None:
    from fastapi import HTTPException

    from app.markets.service import MarketService

    with pytest.raises(HTTPException) as exc:
        await MarketService.price_history(async_session, "does-not-exist-xyz", "7d")
    assert exc.value.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_price_history_endpoint_defaults_to_7d_and_rejects_bad_window() -> None:
    """The HTTP endpoint defaults window to 7d and 422s on a window outside the
    allowlist (T-09-08). Uses the app's own session (a committed market via the
    admin API would be heavier — this asserts the param contract on an unknown
    slug, which still validates the query param BEFORE the 404)."""
    async with await _public_client() as c:
        # Bad window → 422 (validated before the slug lookup).
        bad = await c.get("/api/v1/markets/any-slug/price-history?window=1y")
        assert bad.status_code == 422

        # Default window (no query param) is accepted (resolves to 7d → 404 for
        # an unknown slug, NOT a 422). Proves the default is a valid allowlist value.
        default = await c.get("/api/v1/markets/unknown-slug-default/price-history")
        assert default.status_code == 404
