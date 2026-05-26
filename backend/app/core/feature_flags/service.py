"""FeatureFlagService — minimal v1 (no cache) per D-38 / PLT-06.

Tenant-fallback: prefer a tenant-specific row over the default-tenant row. v1
only ever finds the default row because no per-tenant overrides exist yet;
v2 multi-tenant will start populating tenant rows without changing this API.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.feature_flags.models import FeatureFlag


class FeatureFlagService:
    """Tenant-aware feature-flag reader. Default-deny on missing keys."""

    @staticmethod
    async def is_enabled(
        session: AsyncSession,
        key: str,
        tenant_id: UUID | None = None,
    ) -> bool:
        """Return whether ``key`` is enabled for the given tenant.

        Returns ``False`` when the key has no row (default-deny). When
        ``tenant_id`` matches an explicit row, that row wins over the
        default-tenant row.
        """
        settings = get_settings()
        default_tenant = settings.TENANT_ID_DEFAULT
        target_tenant = tenant_id or default_tenant

        candidates = {target_tenant, default_tenant}
        stmt = select(FeatureFlag).where(
            FeatureFlag.key == key,
            FeatureFlag.tenant_id.in_(candidates),
        )
        rows = (await session.execute(stmt)).scalars().all()
        if not rows:
            return False

        # Prefer the tenant-specific row if present.
        for row in rows:
            if row.tenant_id == target_tenant:
                return bool(row.enabled)
        # Fall back to the default-tenant row.
        return bool(rows[0].enabled)
