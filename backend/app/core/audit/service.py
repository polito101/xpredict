"""AuditService — the SINGLE allowed entry point for inserting audit rows (D-20, D-21).

Phases 2-10 MUST NOT run raw ``INSERT INTO audit_log`` from any code path. Use
``AuditService.record()``. The audit row commits atomically with the underlying
action because the caller passes its own ``AsyncSession`` — no async event bus,
no background queue.

Signature is locked here (Phase 2 CONTEXT.md depends on it):

    AuditService.record(session, *, actor, event_type, payload, ip=None, tenant_id=None) -> AuditLog
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.models import AuditLog
from app.core.config import Settings


class AuditService:
    """Append-only audit-log writer. Caller controls the transaction."""

    @staticmethod
    async def record(
        session: AsyncSession,
        *,
        actor: str,
        event_type: str,
        payload: dict[str, Any],
        ip: str | None = None,
        tenant_id: UUID | None = None,
    ) -> AuditLog:
        """Insert an audit row into the caller's transaction.

        The caller MUST commit (or rollback) the session itself — this method
        only flushes the new row so its server-defaulted ``id`` and
        ``occurred_at`` are populated. The audit row + underlying action
        therefore commit atomically, which is the whole point of this API
        (D-21).

        If ``tenant_id`` is not provided, falls back to
        ``Settings.TENANT_ID_DEFAULT`` (D-22). v2 multi-tenant will swap the
        fallback to a contextvar lookup with this same signature.
        """
        row = AuditLog(
            actor=actor,
            event_type=event_type,
            payload=payload,
            ip=ip,
            tenant_id=tenant_id or Settings().TENANT_ID_DEFAULT,
        )
        session.add(row)
        await session.flush()
        return row
