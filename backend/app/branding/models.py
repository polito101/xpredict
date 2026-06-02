"""TenantConfig — the single-row branding model (Phase 10, Plan 10-01, D-07).

One row holds the operator's white-label branding: brand name, primary/secondary
palette hex, and an optional logo stored as bytes in-row (D-08 — no object storage
in the v1 stack). The ``tenant_id`` ghost column + a ``UNIQUE(tenant_id)``
constraint enforce the single row in v1 and are the seam toward multi-tenant v2
("one row per tenant"). Column / ghost / timestamp shape mirrors ``Market``
(``app/markets/models.py``) verbatim.

``from __future__ import annotations`` is fine in model files (only routers forbid
it — the FastAPI ``Annotated[T, Depends(...)]`` forward-ref hazard).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID as PyUUID
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.db.base import Base


class TenantConfig(Base):
    __tablename__ = "tenant_config"
    __table_args__ = (
        # Single-row in v1; the v2 multi-tenant seam ("one row per tenant", D-07).
        UniqueConstraint("tenant_id", name="tenant_config_tenant_id_key"),
    )

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )
    brand_name: Mapped[str] = mapped_column(Text, nullable=False)
    primary_hex: Mapped[str] = mapped_column(String(7), nullable=False)  # '#rrggbb'
    secondary_hex: Mapped[str] = mapped_column(String(7), nullable=False)
    # Logo bytes live in-row (D-08); served via GET /branding/logo, never inlined
    # into the /branding/current JSON (Pitfall 7).
    logo_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    logo_content_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    # tenant_id ghost — VERBATIM from Market (CONVENTIONS §2 / D-42).
    tenant_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        default=lambda: get_settings().TENANT_ID_DEFAULT,
    )


__all__ = ["TenantConfig"]
