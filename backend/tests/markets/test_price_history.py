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
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

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


async def _seed_polymarket_style_market_with_snapshots(
    session: AsyncSession,
    *,
    snapshot_count: int,
    yes_label: str = "Yes",
    no_label: str = "No",
    interval_minutes: int = 5,
) -> str:
    """Seed one OPEN Polymarket-sourced market whose YES outcome label is stored
    TITLE-CASE ("Yes"/"No"), mirroring how ``PolymarketAdapter.sync_top25`` persists
    the Gamma API's ``outcomes`` array verbatim (``label[:50]``, never normalized).

    Attaches ``snapshot_count`` OddsSnapshot rows to the YES leg. Returns the slug.
    Rows are NOT committed — the caller's ``async_session`` fixture rolls back on
    teardown. Regression seed for IN-01 (case-insensitive YES selection).
    """
    from app.markets.enums import MarketSourceEnum, MarketStatus
    from app.markets.models import Market, OddsSnapshot, Outcome, generate_slug

    market = Market(
        question="Will the title-case market chart?",
        slug=generate_slug("Will the title-case market chart"),
        resolution_criteria="resolves via Polymarket UMA oracle",
        category="test",
        source=MarketSourceEnum.POLYMARKET.value,
        status=MarketStatus.OPEN.value,
        deadline=datetime.now(UTC) + timedelta(days=2),
    )
    session.add(market)
    await session.flush()

    yes = Outcome(
        market_id=market.id,
        label=yes_label,
        initial_odds=Decimal("0.500000"),
        current_odds=Decimal("0.500000"),
    )
    no = Outcome(
        market_id=market.id,
        label=no_label,
        initial_odds=Decimal("0.500000"),
        current_odds=Decimal("0.500000"),
    )
    session.add_all([yes, no])
    await session.flush()

    start = datetime.now(UTC) - timedelta(minutes=interval_minutes * snapshot_count)
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
async def test_price_history_titlecase_yes_label_returns_points(
    async_session: AsyncSession,
) -> None:
    """IN-01 regression: a Polymarket-style market whose YES outcome is stored
    TITLE-CASE ("Yes") must still return a NON-empty price-history series.

    Before the fix, ``price_history`` selected the YES leg with a case-sensitive
    ``Outcome.label == "YES"`` filter, which matched house markets ("YES") but
    silently returned NULL for Polymarket-mirrored markets ("Yes") — so their
    detail-page chart rendered empty. This test FAILS without the case-insensitive
    ``func.upper(Outcome.label) == "YES"`` selection and PASSES with it.
    """
    from app.markets.service import MarketService

    slug = await _seed_polymarket_style_market_with_snapshots(
        async_session, snapshot_count=6, yes_label="Yes", no_label="No"
    )

    resp = await MarketService.price_history(async_session, slug, "7d")
    assert resp.window == "7d"
    # The series is non-empty — the title-case YES leg was selected (IN-01 fixed).
    assert len(resp.points) == 6
    # Probabilities still serialize to JSON strings on the wire (SP-1) — unchanged.
    dumped = json.loads(resp.model_dump_json())
    assert all(isinstance(p["probability"], str) for p in dumped["points"])
    # Ordered ascending by ts (raw 7d window — no bucketing).
    assert [p.ts for p in resp.points] == sorted(p.ts for p in resp.points)


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_price_history_uppercase_house_label_still_returns_points(
    async_session: AsyncSession,
) -> None:
    """IN-01 must NOT regress house markets: a market whose YES outcome is the
    canonical upper-case "YES" still returns its full series (case-insensitive
    selection preserves exact behavior for existing house markets)."""
    from app.markets.service import MarketService

    slug = await _seed_market_with_snapshots(async_session, snapshot_count=4)
    resp = await MarketService.price_history(async_session, slug, "7d")
    assert len(resp.points) == 4


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_update_market_titlecase_yes_targets_yes_leg(
    async_session: AsyncSession,
) -> None:
    """IN-01 (service.py:160): an admin ``odds_yes`` edit on a Polymarket-style
    market whose YES leg is title-case "Yes" must update THAT leg, not silently
    assign ``odds_no`` to both. Before the fix the case-sensitive ``== "YES"``
    missed the "Yes" leg, so both outcomes received ``1 - odds_yes``.
    """
    from app.auth.models import User
    from app.markets.enums import MarketSourceEnum, MarketStatus
    from app.markets.models import Market, Outcome, generate_slug
    from app.markets.schemas import MarketUpdate
    from app.markets.service import MarketService

    admin = User(
        email="in01-admin@test.com",
        hashed_password="not-a-real-hash",
        is_active=True,
        is_superuser=True,
        is_verified=True,
        display_name="IN-01 Admin",
    )
    async_session.add(admin)
    await async_session.flush()

    market = Market(
        question="Title-case admin-edit market?",
        slug=generate_slug("Title-case admin-edit market"),
        resolution_criteria="resolves via Polymarket UMA oracle",
        category="test",
        source=MarketSourceEnum.POLYMARKET.value,
        status=MarketStatus.OPEN.value,
        deadline=datetime.now(UTC) + timedelta(days=2),
    )
    async_session.add(market)
    await async_session.flush()
    yes = Outcome(
        market_id=market.id,
        label="Yes",
        initial_odds=Decimal("0.500000"),
        current_odds=Decimal("0.500000"),
    )
    no = Outcome(
        market_id=market.id,
        label="No",
        initial_odds=Decimal("0.500000"),
        current_odds=Decimal("0.500000"),
    )
    async_session.add_all([yes, no])
    await async_session.flush()

    await MarketService.update_market(
        async_session,
        market,
        MarketUpdate(odds_yes=Decimal("0.700000")),
        admin,
    )
    await async_session.refresh(yes)
    await async_session.refresh(no)
    # The title-case YES leg got the new odds; NO got the complement (1 - 0.7).
    assert yes.current_odds == Decimal("0.700000")
    assert no.current_odds == Decimal("0.300000")


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


# ---------------------------------------------------------------------------
# Integration — live HTTP endpoint over a COMMITTED 30-day backfill (ROADMAP SC#2)
# ---------------------------------------------------------------------------
#
# The ASGITransport client uses the app's OWN db session (committed rows), not the
# rolled-back ``async_session`` fixture — so these tests seed via the ``engine`` and
# clean up in a finally block, mirroring ``test_public_router.py``.


async def _engine_seed_backfill(
    engine: AsyncEngine,
    *,
    snapshot_count: int,
    interval_minutes: int = 5,
) -> tuple[str, str]:
    """COMMIT one OPEN house market (YES/NO) + ``snapshot_count`` YES OddsSnapshot
    rows at ``interval_minutes`` spacing. Returns ``(market_id, slug)``."""
    from app.markets.models import generate_slug

    slug = generate_slug("HTTP backfill market")
    span_start = datetime.now(UTC) - timedelta(minutes=interval_minutes * snapshot_count)
    async with engine.connect() as conn:
        market_id = (
            await conn.execute(
                text(
                    "INSERT INTO markets (question, slug, resolution_criteria, category,"
                    " source, status, deadline) VALUES "
                    "('HTTP backfill?', :slug, 'resolves', 'test', 'HOUSE', 'OPEN', :dl)"
                    " RETURNING id"
                ),
                {"slug": slug, "dl": datetime.now(UTC) + timedelta(days=2)},
            )
        ).scalar_one()
        yes_id = (
            await conn.execute(
                text(
                    "INSERT INTO outcomes (market_id, label, initial_odds, current_odds)"
                    " VALUES (:mid, 'YES', 0.5, 0.5) RETURNING id"
                ),
                {"mid": market_id},
            )
        ).scalar_one()
        await conn.execute(
            text(
                "INSERT INTO outcomes (market_id, label, initial_odds, current_odds)"
                " VALUES (:mid, 'NO', 0.5, 0.5)"
            ),
            {"mid": market_id},
        )
        for i in range(snapshot_count):
            await conn.execute(
                text(
                    "INSERT INTO odds_snapshots (market_id, outcome_id, probability,"
                    " snapshot_at) VALUES (:mid, :oid, 0.5, :ts)"
                ),
                {
                    "mid": market_id,
                    "oid": yes_id,
                    "ts": span_start + timedelta(minutes=interval_minutes * i),
                },
            )
        await conn.commit()
    return str(market_id), slug


async def _engine_delete_market(engine: AsyncEngine, market_id: str) -> None:
    async with engine.connect() as conn:
        await conn.execute(
            text("DELETE FROM odds_snapshots WHERE market_id = CAST(:mid AS uuid)"),
            {"mid": market_id},
        )
        await conn.execute(
            text("DELETE FROM outcomes WHERE market_id = CAST(:mid AS uuid)"),
            {"mid": market_id},
        )
        await conn.execute(
            text("DELETE FROM markets WHERE id = CAST(:mid AS uuid)"),
            {"mid": market_id},
        )
        await conn.commit()


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_endpoint_30d_backfill_is_downsampled_below_raw_count(
    engine: AsyncEngine,
) -> None:
    """ROADMAP SC#2: a dense 30-day-style 5-min backfill, fetched via the live
    ``?window=30d`` endpoint, returns hourly-bucketed points STRICTLY FEWER than the
    raw 5-min count — proving server-side downsampling fired on the real HTTP path.
    """
    # 24 hours of 5-min snapshots = 288 raw rows over 24 distinct hour-buckets.
    # (A representative dense window keeps the test fast while still proving the
    # bucketed count << raw count; the same SQL handles the full 30-day span.)
    raw_count = 288
    market_id, slug = await _engine_seed_backfill(engine, snapshot_count=raw_count)
    try:
        async with await _public_client() as c:
            resp = await c.get(f"/api/v1/markets/{slug}/price-history?window=30d")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["window"] == "30d"
        points = body["points"]
        # Strictly fewer than the raw 5-min count (downsampling actually reduced it).
        assert len(points) < raw_count
        # ~hourly buckets for a 24h span (allow boundary buckets).
        assert 23 <= len(points) <= 26
        # Each probability is a STRING on the wire (SP-1), never a JSON float.
        assert all(isinstance(p["probability"], str) for p in points)
        # Hourly-spaced: distinct hour-truncated timestamps, ascending.
        ts_list = [datetime.fromisoformat(p["ts"]) for p in points]
        assert ts_list == sorted(ts_list)
        hours = {t.replace(minute=0, second=0, microsecond=0) for t in ts_list}
        assert len(hours) == len(points)
    finally:
        await _engine_delete_market(engine, market_id)


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_endpoint_7d_default_returns_raw_points(engine: AsyncEngine) -> None:
    """GET without a window defaults to 7d and returns raw 5-min points (not bucketed)."""
    market_id, slug = await _engine_seed_backfill(engine, snapshot_count=10)
    try:
        async with await _public_client() as c:
            resp = await c.get(f"/api/v1/markets/{slug}/price-history")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["window"] == "7d"
        # 7d serves RAW rows — all 10 recent 5-min snapshots survive (no bucketing).
        assert len(body["points"]) == 10
    finally:
        await _engine_delete_market(engine, market_id)


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_endpoint_unknown_slug_returns_404(engine: AsyncEngine) -> None:
    async with await _public_client() as c:
        resp = await c.get("/api/v1/markets/definitely-not-a-real-slug/price-history?window=7d")
    assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_bare_slug_route_still_resolves(engine: AsyncEngine) -> None:
    """No route-shadowing regression: GET /{slug} still resolves the bare market
    after adding the /{slug}/price-history + /{slug}/activity sibling routes."""
    market_id, slug = await _engine_seed_backfill(engine, snapshot_count=2)
    try:
        async with await _public_client() as c:
            resp = await c.get(f"/api/v1/markets/{slug}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["slug"] == slug
        assert len(body["outcomes"]) == 2
    finally:
        await _engine_delete_market(engine, market_id)
