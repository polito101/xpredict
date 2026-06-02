"""Shared branding repository helpers (Phase 10, IN-02).

Extracted from admin_router.py and router.py to eliminate duplication of
``_load_singleton`` (verbatim copy in both files) and ``_logo_url_for``
(repeated three times across the two routers before this extraction).

Both routers import from here so any future change to the singleton read
strategy (ORDER BY, index hint, etc.) happens in one place.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.branding.models import TenantConfig


async def load_singleton(session: AsyncSession) -> TenantConfig | None:
    """Load the single tenant_config row (or None on a fresh, unseeded DB).

    Ordered by ``created_at`` so the read is deterministic even if the
    single-row invariant is ever violated (``tenant_id`` is nullable, so
    ``UNIQUE(tenant_id)`` permits multiple ``tenant_id IS NULL`` rows in
    Postgres — WR-03). The admin editor and the public reader then always
    resolve the SAME row.
    """
    return (
        await session.execute(
            select(TenantConfig).order_by(TenantConfig.created_at.asc()).limit(1)
        )
    ).scalar_one_or_none()


def logo_url_for(row: TenantConfig) -> str | None:
    """``/branding/logo`` when a logo is set, else ``None``."""
    return "/branding/logo" if row.logo_bytes is not None else None


__all__ = ["load_singleton", "logo_url_for"]
