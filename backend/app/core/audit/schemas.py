"""Audit-log viewer Pydantic schemas (Phase 8, Plan 08-02, ADD-04).

The audit log is the operator's trust signal (PITFALL #6): "everything is
recorded and immutable". This module is READ-ONLY contract — the viewer renders
``AuditLog`` rows, it never mutates them (immutability is enforced at the DB
layer by the BEFORE UPDATE/DELETE trigger + REVOKE from Phase 1).

``AuditLogItem`` mirrors the ``AuditLog`` ORM model 1:1 with
``from_attributes=True``. Per D-12 the JSONB ``payload`` is exposed as a *raw
JSON object* (``dict[str, Any]``) — no per-event-type parsing/prettifying in v1;
the frontend renders it as a collapsible JSON block.

``KNOWN_EVENT_TYPES`` (D-13) is the hardcoded list of event types emitted by
Phases 1-7 (+ the Phase 8 ban events), consumed by the frontend filter dropdown.
New phases extend this list.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

# D-13: known event types for the audit-log filter dropdown. Sourced from the
# dotted ``domain.action`` taxonomy actually emitted across Phases 1-8. The ban
# events (admin.user_banned / admin.user_unbanned) are the ones Plan 08-01 now
# writes; the rest are the auth / wallet / market / settlement events.
KNOWN_EVENT_TYPES: list[str] = [
    "auth.player_registered",
    "auth.login_started",
    "auth.login_failed",
    "auth.admin_login_started",
    "auth.admin_login_failed",
    "auth.session_revoked",
    "auth.password_reset",
    "auth.email_verified",
    "wallet.recharge",
    "wallet.reconciliation",
    "bet.placed",
    "market.created",
    "market.updated",
    "market.closed",
    "market.resolved",
    "settlement.completed",
    "settlement.reversed",
    "admin.user_banned",
    "admin.user_unbanned",
    "admin.branding_updated",
]


class AuditLogItem(BaseModel):
    """One audit-log row for the read-only viewer (D-11/D-12).

    ``payload`` is the raw JSONB object exactly as stored — the operator inspects
    the full event payload (D-12). ``ip`` is nullable (system/cron events have no
    client IP).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    occurred_at: datetime
    event_type: str
    actor: str
    payload: dict[str, Any]
    ip: str | None = None


__all__ = ["KNOWN_EVENT_TYPES", "AuditLogItem"]
