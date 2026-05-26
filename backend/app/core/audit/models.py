"""AuditLog ORM model (D-19, PLT-02).

Schema is locked here; the Alembic 0001 baseline migration (Plan 01-03) creates
the table to match this declaration. Defense-in-depth immutability lives at the
DB layer (BEFORE UPDATE/DELETE trigger + REVOKE) — see Plan 01-03.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import DateTime, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import Settings
from app.db.base import Base


class AuditLog(Base):
    """Append-only audit row — see D-20 and CONVENTIONS.md §6."""

    __tablename__ = "audit_log"

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    """`user:<uuid>` | `admin` | `system` | `celery:<task_name>` — see CONVENTIONS.md."""

    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    """Dotted lowercase `domain.action`, e.g. `auth.guest_created` (D-40)."""

    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    tenant_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        default=lambda: Settings().TENANT_ID_DEFAULT,
    )
