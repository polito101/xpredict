"""Phase 7 — ADM-06: Admin force-settle endpoint tests.

Integration tests (testcontainers) via the FastAPI ASGI client.
Mirrors the test_settlement_router.py harness.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.auth.deps import current_active_admin
from app.db.session import _get_session_maker
from app.main import app
from app.settlement.router import get_gamma_client, get_market_resolver

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine:
    return engine


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(loop_scope="session")
async def api():
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class FakeMarketResolver:
    def __init__(self) -> None:
        self.resolved: list[tuple[UUID, UUID]] = []
        self.reopened: list[UUID] = []

    async def mark_resolved(self, session, *, market_id: UUID, winning_outcome_id: UUID) -> None:
        self.resolved.append((market_id, winning_outcome_id))

    async def mark_unresolved(self, session, *, market_id: UUID) -> None:
        self.reopened.append(market_id)


class _Admin:
    def __init__(self, user_id: UUID) -> None:
        self.id = user_id


def _admin(user_id: UUID) -> None:
    app.dependency_overrides[current_active_admin] = lambda: _Admin(user_id)


def _resolver(r: FakeMarketResolver) -> None:
    app.dependency_overrides[get_market_resolver] = lambda: r


def _fake_gamma(uma_status: str | None = "disputed") -> None:
    """Override get_gamma_client to return a fake with a known UMA status."""
    fake = AsyncMock()
    fake.fetch_market_by_id = AsyncMock(
        return_value={"umaResolutionStatus": uma_status} if uma_status else None
    )
    fake.close = AsyncMock()
    app.dependency_overrides[get_gamma_client] = lambda: fake


async def _seed_polymarket_market() -> tuple[UUID, UUID]:
    """Insert a Polymarket-sourced market with one outcome. Returns (market_id, outcome_id)."""
    from app.markets.enums import MarketSourceEnum, MarketStatus
    from app.markets.models import Market, Outcome

    market_id = uuid4()
    outcome_id = uuid4()
    sm = _get_session_maker()
    async with sm() as s, s.begin():
        mkt = Market(
            id=market_id,
            question=f"Force settle test {market_id.hex[:8]}",
            slug=f"force-settle-{market_id.hex[:8]}",
            resolution_criteria="test",
            source=MarketSourceEnum.POLYMARKET.value,
            source_market_id=f"gamma-{market_id.hex[:8]}",
            status=MarketStatus.OPEN.value,
            deadline=datetime.now(UTC) - timedelta(hours=1),
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

    return market_id, outcome_id


async def _seed_house_market() -> tuple[UUID, UUID]:
    """Insert a HOUSE-sourced market (force-settle should 404 these)."""
    from app.markets.enums import MarketSourceEnum, MarketStatus
    from app.markets.models import Market, Outcome

    market_id = uuid4()
    outcome_id = uuid4()
    sm = _get_session_maker()
    async with sm() as s, s.begin():
        mkt = Market(
            id=market_id,
            question=f"House market {market_id.hex[:8]}",
            slug=f"house-{market_id.hex[:8]}",
            resolution_criteria="test",
            source=MarketSourceEnum.HOUSE.value,
            source_market_id=None,
            status=MarketStatus.OPEN.value,
            deadline=datetime.now(UTC) + timedelta(days=1),
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

    return market_id, outcome_id


async def test_force_settle_requires_admin(api: httpx.AsyncClient) -> None:
    """No admin Bearer -> 401 (SC#5 auth gate)."""
    market_id, outcome_id = await _seed_polymarket_market()
    r = await api.post(
        f"/admin/markets/{market_id}/force-settle",
        json={"winning_outcome_id": str(outcome_id), "justification": "test override"},
    )
    assert r.status_code == 401


async def test_force_settle_rejects_house_market(api: httpx.AsyncClient) -> None:
    """force-settle returns 404 for HOUSE-sourced markets (T-07-08)."""
    market_id, outcome_id = await _seed_house_market()
    admin_id = uuid4()
    _admin(admin_id)
    _fake_gamma()
    _resolver(FakeMarketResolver())

    r = await api.post(
        f"/admin/markets/{market_id}/force-settle",
        json={"winning_outcome_id": str(outcome_id), "justification": "test override"},
    )
    assert r.status_code == 404


async def test_force_settle_rejects_unknown_market(api: httpx.AsyncClient) -> None:
    """force-settle returns 404 for unknown market ids."""
    _admin(uuid4())
    _fake_gamma()
    _resolver(FakeMarketResolver())

    r = await api.post(
        f"/admin/markets/{uuid4()}/force-settle",
        json={"winning_outcome_id": str(uuid4()), "justification": "test override"},
    )
    assert r.status_code == 404


async def test_force_settle_audit_entry(api: httpx.AsyncClient) -> None:
    """force-settle writes a polymarket_admin_override audit row (SC#5)."""
    from sqlalchemy import select

    from app.core.audit.models import AuditLog

    market_id, outcome_id = await _seed_polymarket_market()
    admin_id = uuid4()
    _admin(admin_id)
    _fake_gamma(uma_status="disputed")
    _resolver(FakeMarketResolver())

    r = await api.post(
        f"/admin/markets/{market_id}/force-settle",
        json={
            "winning_outcome_id": str(outcome_id),
            "justification": "Admin override for stuck market",
        },
    )
    assert r.status_code == 200, r.text

    # Verify audit row was written.
    sm = _get_session_maker()
    async with sm() as s:
        row = (
            await s.execute(
                select(AuditLog)
                .where(AuditLog.event_type == "polymarket_admin_override")
                .order_by(AuditLog.occurred_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    assert row is not None, "polymarket_admin_override audit row must be written"
    assert row.payload["market_id"] == str(market_id)
    assert row.payload["admin_id"] == str(admin_id)
    assert "Admin override" in row.payload["justification"]


async def test_force_settle_captures_uma_status(api: httpx.AsyncClient) -> None:
    """force-settle captures the live Gamma umaResolutionStatus at override time (SC#5)."""
    from app.core.audit.models import AuditLog

    market_id, outcome_id = await _seed_polymarket_market()
    _admin(uuid4())
    _fake_gamma(uma_status="disputed")
    _resolver(FakeMarketResolver())

    r = await api.post(
        f"/admin/markets/{market_id}/force-settle",
        json={
            "winning_outcome_id": str(outcome_id),
            "justification": "UMA status capture test",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Response reflects the captured status.
    assert body["uma_status_at_override"] == "disputed"

    # Audit row captures it too.
    sm = _get_session_maker()
    async with sm() as s:
        row = (
            await s.execute(
                select(AuditLog)
                .where(AuditLog.event_type == "polymarket_admin_override")
                .where(AuditLog.payload["market_id"].as_string() == str(market_id))
                .limit(1)
            )
        ).scalar_one_or_none()

    assert row is not None
    assert row.payload["uma_status_at_override_time"] == "disputed"
