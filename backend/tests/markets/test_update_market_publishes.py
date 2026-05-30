"""Producer hook #1 (MKT-04): admin odds edit publishes a lean delta POST-COMMIT.

T-09-03: the PATCH /api/v1/admin/markets/{id} odds branch must call
publish_odds_change_threadsafe exactly once AFTER session.commit(), with string
odds for both YES and NO outcomes — and must NOT publish when the PATCH body
carries no odds_yes. (The route awaits the threadsafe wrapper — WR-02 — which
offloads the blocking sync publish to a worker thread; the same call contract.)
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.markets.test_admin_router import (
    _ADMIN_EMAIL,
    _auth,
    _cleanup_user,
    _client,
    _get_admin_token,
    _market_body,
    _seed_user,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


async def test_odds_edit_publishes_once_post_commit(engine: AsyncEngine) -> None:
    """A PATCH with odds_yes publishes exactly one delta with string YES+NO odds.

    The publish is patched at its router import site. Because the router calls it
    only after ``await session.commit()``, a recorded call proves a post-commit
    publish; we additionally assert the committed odds are readable from the DB
    (so the delta reflects committed — not rolled-back — state, T-09-03).
    """
    await _seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await _client() as c:
            token = await _get_admin_token(c)
            create_resp = await c.post(
                "/api/v1/admin/markets",
                json=_market_body(),
                headers=_auth(token),
            )
            market_id = create_resp.json()["id"]

            with patch(
                "app.markets.router.publish_odds_change_threadsafe"
            ) as mock_publish:
                resp = await c.patch(
                    f"/api/v1/admin/markets/{market_id}",
                    json={"odds_yes": "0.7"},
                    headers=_auth(token),
                )

        assert resp.status_code == 200, resp.text

        # Published (awaited) exactly once — patching an async def yields an
        # AsyncMock, so assert on the await.
        mock_publish.assert_awaited_once()
        call_args = mock_publish.call_args
        published_market_id = call_args.args[0]
        deltas = call_args.args[1]
        assert str(published_market_id) == market_id

        # Lean delta: string odds for YES (0.7) and NO (0.3), keyed by outcome_id.
        by_odds = {d["odds"]: d for d in deltas}
        assert len(deltas) == 2
        assert {d["odds"] for d in deltas} == {"0.700000", "0.300000"}
        for d in deltas:
            assert set(d.keys()) == {"outcome_id", "odds"}
            assert isinstance(d["odds"], str)
            assert isinstance(d["outcome_id"], str)

        # Post-commit: the committed YES odds are readable from the DB.
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT label, current_odds FROM outcomes"
                        " WHERE market_id = :mid ORDER BY label"
                    ),
                    {"mid": market_id},
                )
            ).all()
        odds_by_label = {label: Decimal(str(odds)) for label, odds in rows}
        assert odds_by_label["YES"] == Decimal("0.700000")
        assert odds_by_label["NO"] == Decimal("0.300000")
        # The delta matches the committed DB odds (no ghost/rolled-back price).
        assert by_odds["0.700000"] is not None
    finally:
        await _cleanup_user(engine, _ADMIN_EMAIL)


async def test_non_odds_patch_does_not_publish(engine: AsyncEngine) -> None:
    """A PATCH with no odds_yes (criteria-only) publishes zero times."""
    await _seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await _client() as c:
            token = await _get_admin_token(c)
            create_resp = await c.post(
                "/api/v1/admin/markets",
                json=_market_body(),
                headers=_auth(token),
            )
            market_id = create_resp.json()["id"]

            with patch(
                "app.markets.router.publish_odds_change_threadsafe"
            ) as mock_publish:
                resp = await c.patch(
                    f"/api/v1/admin/markets/{market_id}",
                    json={"resolution_criteria": "Updated criteria only"},
                    headers=_auth(token),
                )

        assert resp.status_code == 200, resp.text
        mock_publish.assert_not_awaited()
    finally:
        await _cleanup_user(engine, _ADMIN_EMAIL)
