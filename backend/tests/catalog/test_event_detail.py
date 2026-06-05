"""Event detail endpoint tests (BRW-02 + EVT-07 ≥2-child gating).

``GET /api/v1/events/{slug}`` returns per-outcome YES rows + the derived status for a
≥2-child group, and 404s a 1-child group (EVT-07: a single-outcome group stays on
the standalone ``/markets/{slug}`` path) or a missing slug. Shared-session override
pattern (see ``test_catalog_router`` docstring).
"""

from __future__ import annotations

import pytest

from app.db.session import get_async_session
from app.main import app
from tests.catalog._factories import make_event, make_single_child_group

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


async def test_event_detail_two_child(api, async_session) -> None:
    app.dependency_overrides[get_async_session] = lambda: async_session
    group, _children = await make_event(
        async_session, title="Cup winner?", n_outcomes=3, labels=["Alpha", "Bravo", "Charlie"]
    )
    await async_session.flush()

    resp = await api.get(f"/api/v1/events/{group.slug}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == group.slug
    assert body["status"] in ("open", "partially_resolved", "resolved", "void")
    assert body["status"] == "open"  # make_event leaves every child OPEN
    assert len(body["outcomes"]) == 3
    labels = {o["label"] for o in body["outcomes"]}
    assert {"Alpha", "Bravo", "Charlie"} <= labels
    for outcome in body["outcomes"]:
        assert isinstance(outcome["yes_price"], str)  # money as a JSON string
        assert "market_id" in outcome
        assert "child_status" in outcome


async def test_event_detail_single_child_404(api, async_session) -> None:
    app.dependency_overrides[get_async_session] = lambda: async_session
    group, _child = await make_single_child_group(async_session, title="Lonely event?")
    await async_session.flush()

    resp = await api.get(f"/api/v1/events/{group.slug}")
    assert resp.status_code == 404


async def test_event_detail_missing_404(api, async_session) -> None:
    app.dependency_overrides[get_async_session] = lambda: async_session
    resp = await api.get("/api/v1/events/this-slug-does-not-exist-xyz-9000")
    assert resp.status_code == 404
