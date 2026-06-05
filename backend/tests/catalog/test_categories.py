"""Categories union endpoint test (BRW-02 / CAT-06).

Asserts the sorted, DISTINCT, non-empty category union over standalone markets +
event groups, excluding NULL / empty categories. Uses the shared-session override
(see ``test_catalog_router`` docstring); assertions are membership-based so committed
rows leaked by other test modules cannot break them (the NULL/empty exclusion is a
property of the query, independent of leaked data).
"""

from __future__ import annotations

import pytest

from app.db.session import get_async_session
from app.main import app
from tests.catalog._factories import make_event, make_market

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


async def test_categories_union_nonempty(api, async_session) -> None:
    app.dependency_overrides[get_async_session] = lambda: async_session
    await make_market(async_session, question="Politics market?", category="Politics")
    await make_market(async_session, question="No category market?", category=None)
    await make_market(async_session, question="Empty category market?", category="")
    await make_event(async_session, title="Sports event?", category="Sports", n_outcomes=2)
    await make_event(async_session, title="Crypto event?", category="Crypto", n_outcomes=2)
    await async_session.flush()

    resp = await api.get("/api/v1/categories")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    # Non-empty categories from BOTH markets and groups appear.
    assert "Politics" in body  # market category
    assert "Sports" in body  # group category
    assert "Crypto" in body  # group category
    # CAT-06: NULL / empty categories are excluded.
    assert None not in body
    assert "" not in body
    # Sorted + DISTINCT (no duplicates).
    assert body == sorted(set(body))
