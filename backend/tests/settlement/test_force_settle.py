"""Phase 7 — ADM-06: Admin force-settle endpoint tests.

These stubs are Wave 0 scaffolds; the real implementations are filled by Plan 07-03.
"""

from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.mark.skip(reason="Wave 0 scaffold — filled by Plan 07-03")
async def test_force_settle_audit_entry() -> None:
    """Force-settle writes a polymarket_admin_override audit row with justification and admin_id (SC#5)."""


@pytest.mark.skip(reason="Wave 0 scaffold — filled by Plan 07-03")
async def test_force_settle_captures_uma_status() -> None:
    """Force-settle captures the live Gamma umaResolutionStatus at override time (SC#5)."""


@pytest.mark.skip(reason="Wave 0 scaffold — filled by Plan 07-03")
async def test_force_settle_requires_admin() -> None:
    """No admin Bearer → 401; non-Polymarket market → 404."""
