"""Integration tests — PLT-06 (feature flags + seed + tenant fallback).

Same testcontainers Postgres backing as ``test_audit_immutability.py``. The
session-scoped ``engine`` fixture has already run ``alembic upgrade head``
so the 3 seeded rows from D-39 are present.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.feature_flags.service import FeatureFlagService

pytestmark = [
    pytest.mark.integration,
    # Share the session-scoped event loop with the engine + async_session
    # fixtures (pytest-asyncio 0.25: fixtures and tests must agree on loop
    # scope or asyncpg connections get cross-loop "Event loop is closed").
    pytest.mark.asyncio(loop_scope="session"),
]


# ---------------------------------------------------------------------------
# D-39 seed rows present
# ---------------------------------------------------------------------------


async def test_seed_flags(async_session: AsyncSession) -> None:
    """The 3 seed flags exist after ``alembic upgrade head`` (D-39, PLT-06)."""
    rows = (
        await async_session.execute(
            text("SELECT key, enabled FROM feature_flags ORDER BY key")
        )
    ).all()
    # Convert to dict for stable assertions
    seeded = {row[0]: row[1] for row in rows}
    assert seeded == {
        "admin_2fa_required": False,
        "polymarket_sync_enabled": False,
        "stripe_recharge_enabled": False,
    }


# ---------------------------------------------------------------------------
# FeatureFlagService.is_enabled returns seeded values
# ---------------------------------------------------------------------------


async def test_is_enabled_returns_seeded_value(async_session: AsyncSession) -> None:
    """Default-tenant seeded value is what ``is_enabled`` returns (D-38)."""
    assert (
        await FeatureFlagService.is_enabled(async_session, "stripe_recharge_enabled")
        is False
    )
    assert (
        await FeatureFlagService.is_enabled(async_session, "polymarket_sync_enabled")
        is False
    )
    assert (
        await FeatureFlagService.is_enabled(async_session, "admin_2fa_required")
        is False
    )


# ---------------------------------------------------------------------------
# Toggle via UPDATE flips is_enabled
# ---------------------------------------------------------------------------


async def test_is_enabled_toggle(async_session: AsyncSession) -> None:
    """Flipping ``enabled`` via UPDATE makes ``is_enabled`` return True."""
    await async_session.execute(
        text(
            """
            UPDATE feature_flags
            SET enabled = TRUE
            WHERE key = 'stripe_recharge_enabled'
            """
        )
    )
    assert (
        await FeatureFlagService.is_enabled(async_session, "stripe_recharge_enabled")
        is True
    )


# ---------------------------------------------------------------------------
# Unknown key defaults to False (default-deny per D-38)
# ---------------------------------------------------------------------------


async def test_is_enabled_unknown_key_defaults_false(
    async_session: AsyncSession,
) -> None:
    """No matching row → ``is_enabled`` returns False (default-deny)."""
    assert (
        await FeatureFlagService.is_enabled(async_session, "nonexistent_key") is False
    )


# ---------------------------------------------------------------------------
# Tenant fallback to default-tenant row
# ---------------------------------------------------------------------------


async def test_tenant_fallback(async_session: AsyncSession) -> None:
    """Unknown tenant_id falls back to the default-tenant row (D-38)."""
    unknown_tenant = UUID("99999999-9999-9999-9999-999999999999")
    # Only the default-tenant row exists for these seed keys; tenant
    # fallback should still return the default's value (False).
    assert (
        await FeatureFlagService.is_enabled(
            async_session,
            "stripe_recharge_enabled",
            tenant_id=unknown_tenant,
        )
        is False
    )
    # Also verify the seed never duplicated under another tenant.
    rows = (
        await async_session.execute(
            text(
                """
                SELECT COUNT(*) FROM feature_flags
                WHERE key = 'stripe_recharge_enabled'
                """
            )
        )
    ).scalar_one()
    assert rows == 1
