"""Catalog browse/search/filter/sort integration tests (BRW-01/03/04/05).

Isolation: each test overrides ``get_async_session`` so the ``api`` client and the
seed factories share ONE rolled-back ``async_session`` (the catalog conftest's
autouse ``_clear_overrides`` wipes the override after each test). Seeding rides that
session (flush-only); the api SELECT sees the flushed rows within the same
transaction and teardown rolls everything back — no cross-test leakage from this
module. Assertions are written to tolerate committed rows leaked by other test
modules (they use membership / exotic-filter checks, never exact full-list equality
on populated queries).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.db.session import get_async_session
from app.main import app
from tests.catalog._factories import (
    drive_event_partial,
    drive_event_void,
    make_event,
    make_market,
    make_single_child_group,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


def _use(async_session) -> None:
    """Route the app's get_async_session dependency through the test's session."""
    app.dependency_overrides[get_async_session] = lambda: async_session


def _titles(resp) -> list[str]:
    assert resp.status_code == 200, (resp.status_code, resp.text)
    return [item["title"] for item in resp.json()]


def _near() -> datetime:
    return datetime.now(UTC) + timedelta(hours=12)  # within the 48h closing window


def _far() -> datetime:
    return datetime.now(UTC) + timedelta(days=10)  # outside the closing window


async def test_catalog_returns_bounded_list(api, async_session) -> None:
    _use(async_session)
    await make_market(async_session, question="Will it rain in Madrid tomorrow?")
    await make_event(async_session, title="Who wins the league?", n_outcomes=3)
    await make_single_child_group(async_session, title="Solo placeholder event")
    await async_session.flush()

    resp = await api.get("/api/v1/catalog")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) <= 100  # BRW-05 bounded
    assert len(body) >= 2  # the market + the 3-outcome event
    assert {item["type"] for item in body} <= {"market", "event"}
    # A 1-child group must NOT surface as an event item (EVT-07).
    event_titles = [it["title"] for it in body if it["type"] == "event"]
    assert "Solo placeholder event" not in event_titles
    for item in body:  # money on the wire is a JSON string
        assert isinstance(item["volume"], str)


async def test_search_local_only(api, async_session) -> None:
    # BRW-01: a unique token matches via LOCAL ILIKE; the non-matching market is excluded.
    # The catalog service issues no Gamma /public-search proxy (search is pg_trgm local);
    # this test never patches a Gamma client and the result is purely local.
    _use(async_session)
    await make_market(async_session, question="Zorptastic widget launch in Q3?")
    await make_market(async_session, question="Completely separate weather market?")
    await async_session.flush()

    body = (await api.get("/api/v1/catalog", params={"q": "zorptastic"})).json()
    titles = [it["title"] for it in body]
    assert any("Zorptastic" in t for t in titles)
    assert all("separate weather" not in t for t in titles)


async def test_status_filter(api, async_session) -> None:
    # BRW-03 + the derived-event mapping (partially_resolved -> open, void -> resolved).
    _use(async_session)
    await make_market(async_session, question="Open far market?", deadline=_far())
    await make_market(async_session, question="Closing soon market?", deadline=_near())
    await make_market(
        async_session, question="Resolved market?", status="RESOLVED", deadline=_far()
    )
    _, partial_children = await make_event(
        async_session, title="Partial event?", n_outcomes=3, deadline=_far()
    )
    await drive_event_partial(async_session, partial_children)
    _, void_children = await make_event(
        async_session, title="Void event?", n_outcomes=2, deadline=_far()
    )
    await drive_event_void(async_session, void_children)
    await async_session.flush()

    open_titles = _titles(await api.get("/api/v1/catalog", params={"status": "open"}))
    assert "Open far market?" in open_titles
    assert "Closing soon market?" in open_titles  # closing_soon ⊂ open (stored OPEN)
    assert "Partial event?" in open_titles  # partially_resolved -> public open
    assert "Resolved market?" not in open_titles
    assert "Void event?" not in open_titles

    resolved_titles = _titles(await api.get("/api/v1/catalog", params={"status": "resolved"}))
    assert "Resolved market?" in resolved_titles
    assert "Void event?" in resolved_titles  # void -> public resolved
    assert "Open far market?" not in resolved_titles
    assert "Partial event?" not in resolved_titles

    closing_titles = _titles(await api.get("/api/v1/catalog", params={"status": "closing_soon"}))
    assert "Closing soon market?" in closing_titles
    assert "Open far market?" not in closing_titles


async def test_sort(api, async_session) -> None:
    # BRW-04: volume / newest / closing_soonest ordering.
    _use(async_session)
    now = datetime.now(UTC)
    hi = await make_market(
        async_session, question="High volume?", volume=Decimal("300"), deadline=now + timedelta(days=9)
    )
    mid = await make_market(
        async_session, question="Mid volume?", volume=Decimal("200"), deadline=now + timedelta(days=5)
    )
    lo = await make_market(
        async_session, question="Low volume?", volume=Decimal("100"), deadline=now + timedelta(days=1)
    )
    # explicit created_at: lo oldest, hi newest
    lo.created_at = now - timedelta(hours=3)
    mid.created_at = now - timedelta(hours=2)
    hi.created_at = now - timedelta(hours=1)
    async_session.add_all([lo, mid, hi])
    await async_session.flush()

    vol = _titles(await api.get("/api/v1/catalog", params={"sort": "volume"}))
    assert vol.index("High volume?") < vol.index("Mid volume?") < vol.index("Low volume?")

    newest = _titles(await api.get("/api/v1/catalog", params={"sort": "newest"}))
    assert newest.index("High volume?") < newest.index("Mid volume?") < newest.index("Low volume?")

    closing = _titles(await api.get("/api/v1/catalog", params={"sort": "closing_soonest"}))
    # lo has the nearest deadline (now+1d), hi the farthest (now+9d)
    assert closing.index("Low volume?") < closing.index("Mid volume?") < closing.index("High volume?")


async def test_empty_combos(api, async_session) -> None:
    # BRW-05: every guaranteed-empty filter combination returns 200 + [] (never an error).
    _use(async_session)
    await make_market(async_session, question="Some unrelated market?", category="sports")
    await async_session.flush()

    combos = [
        {"category": "__nonexistent__", "status": "resolved", "q": "zzzzzzzz"},
        {"q": "no-such-token-xyzzy-qwerty"},
        {"category": "ghost-category-9000"},
        {"status": "closing_soon", "category": "ghost-category-9000"},
    ]
    for params in combos:
        resp = await api.get("/api/v1/catalog", params=params)
        assert resp.status_code == 200, (params, resp.status_code)
        assert resp.json() == [], (params, resp.json())


async def test_bad_status_and_sort_422(api, async_session) -> None:
    _use(async_session)
    assert (await api.get("/api/v1/catalog", params={"status": "bogus"})).status_code == 422
    assert (await api.get("/api/v1/catalog", params={"sort": "bogus"})).status_code == 422
