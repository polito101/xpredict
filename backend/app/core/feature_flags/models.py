"""FeatureFlag ORM model (D-37).

Composite PK ``(key, tenant_id)`` — v1 has one row per key (the default tenant);
v2 multi-tenant allows per-tenant overrides without a schema change. The
``tenant_id`` ghost column follows D-42 / PLT-01.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import Boolean, DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import Settings
from app.db.base import Base


class FeatureFlag(Base):
    """Single feature-flag row. Tenant-scoped via composite PK."""

    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    tenant_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=lambda: Settings().TENANT_ID_DEFAULT,
    )
