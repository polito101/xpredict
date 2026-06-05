"""Admin house-event router tests — create (EVA-01), edit-lock 423 (EVA-02), auth gate.

These endpoints COMMIT (the create writes a group + N children; the PATCH mutates),
so — unlike the catalog read tests — they do NOT override ``get_async_session``: the
``api`` client uses the real request session and commits to the testcontainer DB, and
verification reads happen on a separate ``async_session`` connection (which sees the
committed rows under READ COMMITTED). The edit-lock-after-bet test seeds a real
ledger-backed bet on a COMMITTED session so the endpoint's ``event_has_bets`` EXISTS
query sees it. Committed test rows leak within a pytest session (harmless — assertions
key off the specific group id returned by the create). Per-module run only.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.bets.models import Bet
from app.db.session import _get_session_maker
from app.main import app
from app.markets.models import Market, MarketGroup
from app.settlement.event_router import event_admin_router
from tests.catalog._factories import admin_override, place_bet_on_child

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine:
    """Force the testcontainer Postgres up (and the env/cache it sets) for every test."""
    return engine


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _bets_table(engine: AsyncEngine):
    """Ensure the FK-less ``bets`` table exists (mirrors test_settlement_router)."""
    async with engine.begin() as conn:
        await conn.run_sync(Bet.__table__.create, checkfirst=True)
    yield


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _mount_event_router() -> None:
    """Mount the admin event router on the test app (main.py registration is plan 16-05)."""
    if not any(getattr(r, "path", "").startswith("/admin/events") for r in app.routes):
        app.include_router(event_admin_router)


@pytest_asyncio.fixture(loop_scope="session")
async def api() -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _future(days: int = 2) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


def _create_body(**overrides) -> dict:
    body = {
        "title": "Who wins the championship?",
        "category": "Sports",
        "deadline": _future(),
        "outcomes": [
            {"label": "Alpha", "initial_odds": "0.6"},
            {"label": "Bravo", "initial_odds": "0.3"},
            {"label": "Charlie", "initial_odds": "0.1"},
        ],
    }
    body.update(overrides)
    return body


async def test_create_event_creates_group_and_children(api, async_session) -> None:
    admin_override(uuid4())
    resp = await api.post("/admin/events", json=_create_body())
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert len(data["outcomes"]) == 3
    assert data["source"] == "HOUSE"
    # YES price round-trips the requested initial_odds (as a JSON string).
    alpha = next(o for o in data["outcomes"] if o["label"] == "Alpha")
    assert isinstance(alpha["yes_price"], str)
    assert Decimal(alpha["yes_price"]) == Decimal("0.6")

    # DB read (separate connection sees the committed rows): one HOUSE group + 3
    # children, each with EXACTLY a YES + NO pair (binary-trigger-safe).
    group = (
        await async_session.execute(
            select(MarketGroup)
            .where(MarketGroup.id == data["id"])
            .options(selectinload(MarketGroup.markets).selectinload(Market.outcomes))
        )
    ).scalar_one()
    assert group.source == "HOUSE"
    children = list(group.markets)
    assert len(children) == 3
    for child in children:
        assert child.group_item_title in {"Alpha", "Bravo", "Charlie"}
        assert sorted(o.label for o in child.outcomes) == ["NO", "YES"]


async def test_create_event_rejects_single_outcome(api) -> None:
    admin_override(uuid4())
    body = _create_body(outcomes=[{"label": "Solo", "initial_odds": "0.5"}])
    resp = await api.post("/admin/events", json=body)
    assert resp.status_code == 422


async def test_create_event_rejects_bad_odds(api) -> None:
    admin_override(uuid4())
    body = _create_body(
        outcomes=[{"label": "A", "initial_odds": "1.5"}, {"label": "B", "initial_odds": "0.5"}]
    )
    resp = await api.post("/admin/events", json=body)
    assert resp.status_code == 422


async def test_edit_lock_pre_bet_succeeds(api) -> None:
    admin_override(uuid4())
    created = (await api.post("/admin/events", json=_create_body())).json()
    group_id = created["id"]

    resp = await api.patch(f"/admin/events/{group_id}", json={"title": "Renamed event"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "Renamed event"


async def test_edit_lock_after_bet_returns_423(api) -> None:
    admin_override(uuid4())
    created = (await api.post("/admin/events", json=_create_body())).json()
    group_id = created["id"]

    # Seed a real ledger-backed bet on one child via a COMMITTED session so the
    # endpoint's EXISTS(bets) edit-lock sees it.
    session_maker = _get_session_maker()
    async with session_maker() as seed, seed.begin():
        child = (
            await seed.execute(select(Market).where(Market.group_id == group_id).limit(1))
        ).scalar_one()
        await place_bet_on_child(seed, child, uuid4(), outcome="YES", stake=Decimal("10"))

    resp = await api.patch(f"/admin/events/{group_id}", json={"title": "Too late"})
    assert resp.status_code == 423
    assert resp.json()["detail"]["code"] == "EVENT_LOCKED"


async def test_patch_missing_group_404(api) -> None:
    admin_override(uuid4())
    resp = await api.patch(f"/admin/events/{uuid4()}", json={"title": "ghost"})
    assert resp.status_code == 404


async def test_create_requires_admin(api) -> None:
    # No override + no Bearer → the real current_active_admin gate returns 401.
    resp = await api.post("/admin/events", json=_create_body())
    assert resp.status_code == 401


async def test_patch_requires_admin(api) -> None:
    resp = await api.patch(f"/admin/events/{uuid4()}", json={"title": "nope"})
    assert resp.status_code == 401
