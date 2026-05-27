"""Integration tests — PLT-01 (tenant_id ghost) + PLT-02 (audit immutability + atomicity).

All tests in this file run against testcontainers Postgres 16 (lazy fixture
in ``conftest.py``). They consume the ``async_session`` fixture, which is
function-scoped + wrapped in a transaction that rolls back — clean DB state
between tests without re-running ``alembic upgrade head``.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.models import AuditLog
from app.core.audit.service import AuditService
from app.core.config import Settings

pytestmark = [
    pytest.mark.integration,
    # Share the session-scoped event loop with the engine + async_session
    # fixtures (pytest-asyncio 0.25: fixtures and tests must agree on loop
    # scope or asyncpg connections get cross-loop "Event loop is closed").
    pytest.mark.asyncio(loop_scope="session"),
]


# ---------------------------------------------------------------------------
# PLT-01: tenant_id ghost column default
# ---------------------------------------------------------------------------


async def test_tenant_id_default(async_session: AsyncSession) -> None:
    """INSERT without ``tenant_id`` defaults to ``Settings.TENANT_ID_DEFAULT`` (D-22, PLT-01)."""
    await async_session.execute(
        text(
            """
            INSERT INTO audit_log (actor, event_type, payload)
            VALUES ('system', 'test.tenant_default', '{}'::jsonb)
            """
        )
    )

    row = (
        await async_session.execute(
            text("SELECT tenant_id FROM audit_log WHERE event_type = 'test.tenant_default'")
        )
    ).one()
    tenant_id = row[0]
    assert tenant_id == UUID("00000000-0000-0000-0000-000000000001")
    assert tenant_id == Settings().TENANT_ID_DEFAULT


# ---------------------------------------------------------------------------
# PLT-02: AuditService atomicity (caller-owned transaction)
# ---------------------------------------------------------------------------


async def test_audit_service_record(async_session: AsyncSession) -> None:
    """``AuditService.record()`` inserts via caller's session; row visible after flush."""
    row = await AuditService.record(
        async_session,
        actor="test",
        event_type="test.event",
        payload={"key": "val"},
    )

    # The row is visible WITHIN this transaction even before commit (the
    # caller owns the tx). The rollback in the fixture cleans up after.
    assert row.id is not None, "AuditLog.id must be populated by Python-side default=uuid4 (WR-05)"
    assert row.actor == "test"
    assert row.event_type == "test.event"
    assert row.payload == {"key": "val"}
    assert row.tenant_id == Settings().TENANT_ID_DEFAULT

    # Double-check via a fresh SELECT inside the same session.
    stmt = select(AuditLog).where(AuditLog.event_type == "test.event")
    found = (await async_session.execute(stmt)).scalar_one()
    assert found.actor == "test"
    assert found.payload == {"key": "val"}


# ---------------------------------------------------------------------------
# PLT-02: audit_log immutability — UPDATE blocked (D-20)
# ---------------------------------------------------------------------------


async def test_audit_log_update_blocked(async_session: AsyncSession) -> None:
    """``UPDATE audit_log`` raises: REVOKE + trigger both fire on PUBLIC roles."""
    # Seed one row so the UPDATE has a target.
    await async_session.execute(
        text(
            """
            INSERT INTO audit_log (actor, event_type, payload)
            VALUES ('system', 'test.update_blocked', '{}'::jsonb)
            """
        )
    )

    with pytest.raises(DBAPIError) as exc_info:
        await async_session.execute(
            text(
                """
                UPDATE audit_log SET actor = 'mutated'
                WHERE event_type = 'test.update_blocked'
                """
            )
        )
    msg = str(exc_info.value).lower()
    assert "append-only" in msg or "permission denied" in msg


# ---------------------------------------------------------------------------
# PLT-02: audit_log immutability — DELETE blocked (D-20)
# ---------------------------------------------------------------------------


async def test_audit_log_delete_blocked(async_session: AsyncSession) -> None:
    """``DELETE FROM audit_log`` raises: REVOKE + trigger both fire on PUBLIC roles."""
    await async_session.execute(
        text(
            """
            INSERT INTO audit_log (actor, event_type, payload)
            VALUES ('system', 'test.delete_blocked', '{}'::jsonb)
            """
        )
    )

    with pytest.raises(DBAPIError) as exc_info:
        await async_session.execute(
            text("DELETE FROM audit_log WHERE event_type = 'test.delete_blocked'")
        )
    msg = str(exc_info.value).lower()
    assert "append-only" in msg or "permission denied" in msg
