"""Admin settle router tests — resolve/void/reverse over HTTP with the two-step confirm.

The execute branch drives the real Phase-15 ``EventService`` (which owns per-child
fresh committed sessions), so these tests reuse the ledger-backed seed + drift helpers
from ``test_event_service`` (``_seed_house_event`` / ``_seed_wallet`` / ``_place`` via
``BetService.place_bet`` / ``_assert_ledger_clean`` → spike-004 ``drift_count == 0``).
The ``api`` client uses the real request session (no ``get_async_session`` override) so
the endpoint sees the committed event + bets; auth is bypassed with ``admin_override``.
Per-module run only (Windows-worktree-safe).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

from app.bets.models import Bet
from app.main import app
from app.markets.enums import MarketSourceEnum, MarketStatus
from app.settlement.event_router import event_admin_router
from tests.catalog._factories import admin_override
from tests.settlement.test_event_service import (
    _assert_ledger_clean,
    _market_status,
    _place,
    _seed_house_event,
    _seed_wallet,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine:
    return engine


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _bets_table(engine: AsyncEngine):
    async with engine.begin() as conn:
        await conn.run_sync(Bet.__table__.create, checkfirst=True)
    yield


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _mount_event_router() -> None:
    if not any(getattr(r, "path", "").startswith("/admin/events") for r in app.routes):
        app.include_router(event_admin_router)


@pytest_asyncio.fixture(loop_scope="session")
async def api() -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _resolve(winning_outcome_id, *, confirm: bool, justification: str = "Official result") -> dict:
    return {
        "winning_outcome_id": str(winning_outcome_id),
        "justification": justification,
        "confirm": confirm,
    }


async def test_resolve_preview_does_not_mutate(api) -> None:
    admin_override(uuid4())
    group_id, children, src = await _seed_house_event(3)
    user, _w = await _seed_wallet(Decimal("100.0000"))
    await _place(user, children[0].view, children[0].yes_id, Decimal("10.0000"), src)

    resp = await api.post(
        f"/admin/events/{group_id}/resolve",
        json=_resolve(children[0].yes_id, confirm=False),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["preview"] is True
    assert body["winners"] == 1
    assert body["losers"] == 2
    assert body["projected_status"] == "resolved"
    # The preview mutated nothing — every child is still OPEN.
    for child in children:
        assert await _market_status(child.market_id) == MarketStatus.OPEN.value


async def test_resolve_execute_settles(api) -> None:
    admin_override(uuid4())
    group_id, children, src = await _seed_house_event(3)
    alice, _a = await _seed_wallet(Decimal("100.0000"))
    bob, _b = await _seed_wallet(Decimal("100.0000"))
    await _place(alice, children[0].view, children[0].yes_id, Decimal("40.0000"), src)
    await _place(bob, children[1].view, children[1].yes_id, Decimal("30.0000"), src)

    resp = await api.post(
        f"/admin/events/{group_id}/resolve",
        json=_resolve(children[0].yes_id, confirm=True),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["preview"] is False
    assert body["projected_status"] == "resolved"
    for child in children:
        assert await _market_status(child.market_id) == MarketStatus.RESOLVED.value
    await _assert_ledger_clean()  # spike-004 drift_count == 0


async def test_void_preview_and_execute(api) -> None:
    admin_override(uuid4())
    group_id, children, src = await _seed_house_event(2)
    yes_bettor, _y = await _seed_wallet(Decimal("100.0000"))
    no_bettor, _n = await _seed_wallet(Decimal("100.0000"))
    await _place(yes_bettor, children[0].view, children[0].yes_id, Decimal("20.0000"), src)
    await _place(no_bettor, children[0].view, children[0].no_id, Decimal("20.0000"), src)

    preview = await api.post(f"/admin/events/{group_id}/void", json={"justification": "Cancelled", "confirm": False})
    assert preview.status_code == 200, preview.text
    pbody = preview.json()
    assert pbody["preview"] is True
    assert pbody["winners"] == 0
    assert pbody["losers"] == 2
    assert pbody["projected_status"] == "void"

    execute = await api.post(f"/admin/events/{group_id}/void", json={"justification": "Cancelled", "confirm": True})
    assert execute.status_code == 200, execute.text
    assert execute.json()["projected_status"] == "void"
    for child in children:
        assert await _market_status(child.market_id) == MarketStatus.RESOLVED.value
    await _assert_ledger_clean()


async def test_reverse_preview_and_execute(api) -> None:
    admin_override(uuid4())
    group_id, children, src = await _seed_house_event(2)
    # Bet on EVERY child so reverse reopens them all (a child with no bets to reverse
    # is not reopened, leaving the event partially_resolved — see EventService reverse).
    alice, _a = await _seed_wallet(Decimal("100.0000"))
    bob, _b = await _seed_wallet(Decimal("100.0000"))
    await _place(alice, children[0].view, children[0].yes_id, Decimal("25.0000"), src)
    await _place(bob, children[1].view, children[1].yes_id, Decimal("15.0000"), src)

    # Resolve first (so there is something to reverse).
    resolved = await api.post(
        f"/admin/events/{group_id}/resolve", json=_resolve(children[0].yes_id, confirm=True)
    )
    assert resolved.status_code == 200, resolved.text

    preview = await api.post(
        f"/admin/events/{group_id}/reverse", json={"justification": "Operator error", "confirm": False}
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["preview"] is True
    assert preview.json()["projected_status"] == "open"

    execute = await api.post(
        f"/admin/events/{group_id}/reverse", json={"justification": "Operator error", "confirm": True}
    )
    assert execute.status_code == 200, execute.text
    assert execute.json()["projected_status"] == "open"
    await _assert_ledger_clean()


async def test_value_error_mirrored_409(api) -> None:
    admin_override(uuid4())
    group_id, children, _src = await _seed_house_event(2, source=MarketSourceEnum.POLYMARKET.value)
    bodies = {
        "resolve": _resolve(children[0].yes_id, confirm=False),
        "void": {"justification": "x", "confirm": False},
        "reverse": {"justification": "x", "confirm": False},
    }
    for action, body in bodies.items():
        # preview branch → 409
        prev = await api.post(f"/admin/events/{group_id}/{action}", json=body)
        assert prev.status_code == 409, (action, "preview", prev.text)
        # execute branch → 409 (service ValueError → _map_event_value_error)
        ex = await api.post(f"/admin/events/{group_id}/{action}", json={**body, "confirm": True})
        assert ex.status_code == 409, (action, "execute", ex.text)


async def test_value_error_blank_justification_422(api) -> None:
    admin_override(uuid4())
    group_id, children, _src = await _seed_house_event(2)
    resp = await api.post(
        f"/admin/events/{group_id}/resolve",
        json=_resolve(children[0].yes_id, confirm=True, justification=""),
    )
    assert resp.status_code == 422


async def test_value_error_bad_winning_outcome_422(api) -> None:
    admin_override(uuid4())
    group_id, children, _src = await _seed_house_event(2)
    # The NO leg of a child is not a valid winning outcome (resolve settles the winner on YES).
    resp = await api.post(
        f"/admin/events/{group_id}/resolve",
        json=_resolve(children[0].no_id, confirm=False),
    )
    assert resp.status_code == 422


async def test_value_error_missing_group_404(api) -> None:
    admin_override(uuid4())
    resp = await api.post(
        f"/admin/events/{uuid4()}/resolve",
        json=_resolve(uuid4(), confirm=True),
    )
    assert resp.status_code == 404


async def test_settle_requires_admin(api) -> None:
    # No override / no Bearer → the real current_active_admin gate returns 401.
    gid = uuid4()
    assert (await api.post(f"/admin/events/{gid}/resolve", json=_resolve(uuid4(), confirm=True))).status_code == 401
    assert (await api.post(f"/admin/events/{gid}/void", json={"justification": "x", "confirm": True})).status_code == 401
    assert (await api.post(f"/admin/events/{gid}/reverse", json={"justification": "x", "confirm": True})).status_code == 401
