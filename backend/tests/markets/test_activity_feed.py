"""Recent-activity feed tests (MKT-03, T-09-05 / T-09-06 — anonymization).

The activity feed is anonymized SERVER-SIDE: the query selects only
``stake`` / ``created_at`` / outcome ``label`` and the ``ActivityItem`` schema has
NO ``user_id`` / ``email`` / ``display_name`` field. The browser must never receive
a user identity (CONTEXT Area 1, 09-RESEARCH Pattern 8).

Two layers:

* **unit** (no DB) — the ``ActivityItem`` schema has no user-identity field and
  serializes ``amount`` to a JSON STRING. Satisfies the ``-m "not integration"`` gate.
* **integration** (testcontainers Postgres) — ``recent_activity`` returns the last
  20 bets newest-first mapped to ``{outcome, amount, created_at}`` and the raw JSON
  contains NO user-identity key anywhere (the load-bearing negative assertion).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

# Keys that MUST NEVER appear in the activity payload (T-09-05).
_FORBIDDEN_IDENTITY_KEYS = {"user_id", "email", "display_name", "user"}


# ---------------------------------------------------------------------------
# Unit — schema contract (no DB, satisfies the -m "not integration" gate)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_activity_item_has_no_user_identity_field() -> None:
    """The ActivityItem schema must not define any user-identity field (T-09-05)."""
    from app.markets.schemas import ActivityItem

    field_names = set(ActivityItem.model_fields.keys())
    leaked = field_names & _FORBIDDEN_IDENTITY_KEYS
    assert not leaked, f"ActivityItem leaks user-identity field(s): {leaked}"
    # The allowed anonymized shape.
    assert field_names == {"outcome", "amount", "created_at"}


@pytest.mark.unit
def test_activity_item_serializes_amount_as_string() -> None:
    from app.markets.schemas import ActivityItem

    item = ActivityItem(
        outcome="YES",
        amount=Decimal("50.0000"),
        created_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
    )
    dumped = json.loads(item.model_dump_json())
    assert dumped["amount"] == "50.0000"
    assert isinstance(dumped["amount"], str)
    # tz-aware ISO-8601 (SP-2).
    assert "+00:00" in dumped["created_at"] or dumped["created_at"].endswith("Z")


@pytest.mark.unit
def test_activity_item_never_emits_a_json_float() -> None:
    from app.markets.schemas import ActivityItem

    item = ActivityItem(
        outcome="NO",
        amount=Decimal("12.5"),
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    raw = item.model_dump_json().replace(" ", "")
    assert '"amount":"12.5"' in raw
    assert '"amount":12.5' not in raw


# ---------------------------------------------------------------------------
# Integration — recent_activity service (testcontainers Postgres)
# ---------------------------------------------------------------------------


async def _seed_market_with_bets(
    session: AsyncSession,
    *,
    bet_count: int,
) -> str:
    """Seed one OPEN house market (YES/NO) plus ``bet_count`` Bet rows alternating
    YES/NO, each with a distinct user_id and increasing created_at. Returns the slug.

    ``Bet.user_id`` / ``market_id`` / ``outcome_id`` are plain UUIDs (no DB FK on
    this slice), so inserting Bet rows directly is valid for a read-side test.
    """
    from app.bets.constants import BET_PENDING
    from app.bets.models import Bet
    from app.markets.enums import MarketSourceEnum, MarketStatus
    from app.markets.models import Market, Outcome, generate_slug

    market = Market(
        question="Activity feed market?",
        slug=generate_slug("Activity feed market"),
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

    base_ts = datetime.now(UTC) - timedelta(minutes=bet_count)
    bets = []
    for i in range(bet_count):
        chosen = yes if i % 2 == 0 else no
        bets.append(
            Bet(
                user_id=uuid4(),
                market_id=market.id,
                outcome_id=chosen.id,
                stake=Decimal(f"{10 + i}.0000"),
                odds_at_placement=Decimal("0.500000"),
                status=BET_PENDING,
                created_at=base_ts + timedelta(minutes=i),
            )
        )
    session.add_all(bets)
    await session.flush()
    return market.slug


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_recent_activity_returns_last_20_newest_first(
    async_session: AsyncSession,
) -> None:
    from app.markets.service import MarketService

    slug = await _seed_market_with_bets(async_session, bet_count=25)

    items = await MarketService.recent_activity(async_session, slug, 20)
    # Capped at 20.
    assert len(items) == 20
    # Newest-first (created_at descending).
    created = [i.created_at for i in items]
    assert created == sorted(created, reverse=True)
    # Outcome label is YES/NO; amount is a Decimal mapped from Bet.stake.
    for item in items:
        assert item.outcome in {"YES", "NO"}
        assert isinstance(item.amount, Decimal)


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_recent_activity_payload_has_no_user_identity(
    async_session: AsyncSession,
) -> None:
    """The load-bearing negative assertion (T-09-05): no user_id / email /
    display_name appears ANYWHERE in the serialized JSON of any item."""
    from app.markets.schemas import ActivityItem
    from app.markets.service import MarketService

    slug = await _seed_market_with_bets(async_session, bet_count=5)
    items = await MarketService.recent_activity(async_session, slug, 20)

    # Serialize exactly as the endpoint would (list[ActivityItem]).
    payload = json.loads(
        json.dumps([json.loads(ActivityItem.model_validate(i).model_dump_json()) for i in items])
    )
    assert len(payload) == 5
    for item in payload:
        item_keys = set(item.keys())
        leaked = item_keys & _FORBIDDEN_IDENTITY_KEYS
        assert not leaked, f"activity item leaks user identity: {leaked}"
        assert item_keys == {"outcome", "amount", "created_at"}

    # Belt-and-suspenders: no forbidden key appears as a substring of the raw JSON.
    raw = json.dumps(payload)
    for forbidden in _FORBIDDEN_IDENTITY_KEYS:
        assert forbidden not in raw


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_recent_activity_empty_market_returns_empty_list(
    async_session: AsyncSession,
) -> None:
    from app.markets.service import MarketService

    slug = await _seed_market_with_bets(async_session, bet_count=0)
    items = await MarketService.recent_activity(async_session, slug, 20)
    assert items == []


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_recent_activity_unknown_slug_raises_404(
    async_session: AsyncSession,
) -> None:
    from fastapi import HTTPException

    from app.markets.service import MarketService

    with pytest.raises(HTTPException) as exc:
        await MarketService.recent_activity(async_session, "no-such-market-xyz", 20)
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Integration — live HTTP endpoint, raw-JSON anonymization assertion (T-09-05)
# ---------------------------------------------------------------------------
#
# The ASGITransport client uses the app's OWN committed session, so seed via the
# engine and clean up in finally (mirrors test_public_router.py).


async def _public_client() -> httpx.AsyncClient:
    from app.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _engine_seed_market_with_bets(
    engine: AsyncEngine,
    *,
    bet_count: int,
) -> tuple[str, str]:
    """COMMIT one OPEN house market (YES/NO) + ``bet_count`` Bet rows. Returns
    ``(market_id, slug)``."""
    from app.markets.models import generate_slug

    slug = generate_slug("HTTP activity market")
    base_ts = datetime.now(UTC) - timedelta(minutes=bet_count)
    async with engine.connect() as conn:
        market_id = (
            await conn.execute(
                text(
                    "INSERT INTO markets (question, slug, resolution_criteria, category,"
                    " source, status, deadline) VALUES "
                    "('HTTP activity?', :slug, 'resolves', 'test', 'HOUSE', 'OPEN', :dl)"
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
        no_id = (
            await conn.execute(
                text(
                    "INSERT INTO outcomes (market_id, label, initial_odds, current_odds)"
                    " VALUES (:mid, 'NO', 0.5, 0.5) RETURNING id"
                ),
                {"mid": market_id},
            )
        ).scalar_one()
        for i in range(bet_count):
            oid = yes_id if i % 2 == 0 else no_id
            await conn.execute(
                text(
                    "INSERT INTO bets (user_id, market_id, outcome_id, stake,"
                    " odds_at_placement, status, created_at) VALUES "
                    "(gen_random_uuid(), :mid, :oid, :stake, 0.5, 'PENDING', :ts)"
                ),
                {
                    "mid": market_id,
                    "oid": oid,
                    "stake": Decimal(f"{10 + i}.0000"),
                    "ts": base_ts + timedelta(minutes=i),
                },
            )
        await conn.commit()
    return str(market_id), slug


async def _engine_delete_market(engine: AsyncEngine, market_id: str) -> None:
    async with engine.connect() as conn:
        await conn.execute(
            text("DELETE FROM bets WHERE market_id = CAST(:mid AS uuid)"),
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
async def test_endpoint_activity_returns_last_20_newest_first(engine: AsyncEngine) -> None:
    market_id, slug = await _engine_seed_market_with_bets(engine, bet_count=25)
    try:
        async with await _public_client() as c:
            resp = await c.get(f"/api/v1/markets/{slug}/activity")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body) == 20
        created = [datetime.fromisoformat(item["created_at"]) for item in body]
        assert created == sorted(created, reverse=True)
        # amount is a string on the wire (SP-1).
        assert all(isinstance(item["amount"], str) for item in body)
    finally:
        await _engine_delete_market(engine, market_id)


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_endpoint_activity_raw_json_has_no_user_identity(engine: AsyncEngine) -> None:
    """T-09-05 (load-bearing): parse the RAW HTTP JSON body and assert no
    user_id / email / display_name key appears in any item."""
    market_id, slug = await _engine_seed_market_with_bets(engine, bet_count=5)
    try:
        async with await _public_client() as c:
            resp = await c.get(f"/api/v1/markets/{slug}/activity")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body) == 5
        for item in body:
            keys = set(item.keys())
            leaked = keys & _FORBIDDEN_IDENTITY_KEYS
            assert not leaked, f"activity endpoint leaks user identity: {leaked}"
            assert keys == {"outcome", "amount", "created_at"}
        # No forbidden key as a substring of the raw response text either.
        raw_text = resp.text
        for forbidden in _FORBIDDEN_IDENTITY_KEYS:
            assert forbidden not in raw_text
    finally:
        await _engine_delete_market(engine, market_id)


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_endpoint_activity_unknown_slug_returns_404(engine: AsyncEngine) -> None:
    async with await _public_client() as c:
        resp = await c.get("/api/v1/markets/no-such-activity-slug/activity")
    assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_endpoint_activity_empty_market_returns_empty_list(engine: AsyncEngine) -> None:
    market_id, slug = await _engine_seed_market_with_bets(engine, bet_count=0)
    try:
        async with await _public_client() as c:
            resp = await c.get(f"/api/v1/markets/{slug}/activity")
        assert resp.status_code == 200, resp.text
        assert resp.json() == []
    finally:
        await _engine_delete_market(engine, market_id)
