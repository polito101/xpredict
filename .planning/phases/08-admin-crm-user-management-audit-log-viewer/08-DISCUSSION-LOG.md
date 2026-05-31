# Phase 8: Admin CRM (User Management & Audit Log Viewer) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-28
**Phase:** 08-admin-crm-user-management-audit-log-viewer
**Areas discussed:** Ban/unban management, Admin table design, CSV export, Audit log viewer UX

---

## Mode

User selected "todo en auto" — all 4 gray areas auto-decided by Claude based on project conventions, ROADMAP requirements, prior phase patterns, and codebase analysis.

---

## Ban/Unban Management

| Option | Description | Selected |
|--------|-------------|----------|
| `banned_at` timestamp | Existing column from Phase 2 (D-10), nullable timestamp doubles as state + audit trail | Auto ✓ |
| Separate `status` enum | New column with ACTIVE/BANNED/SUSPENDED states | |
| `is_active` flag reuse | Reuse fastapi-users `is_active` for ban semantics | |

**Decision:** Use existing `banned_at` column. Three enforcement points: login (403), bet placement (reject), admin recharge (reject). Balance frozen, never zeroed. Mandatory reason on ban, optional on unban.

---

## Admin Table Design

| Option | Description | Selected |
|--------|-------------|----------|
| TanStack Table v8 + shadcn | Server-side pagination/search/filter, DataTable component | Auto ✓ |
| Client-side table | Load all data, filter/sort in browser | |

**Decision:** Server-side everything (pagination, search ILIKE, filters, sort ORDER BY). TanStack Table for column definitions + pagination state. Tabbed user detail page (Profile, Wallet, Bets).

---

## CSV Export

| Option | Description | Selected |
|--------|-------------|----------|
| Batch (in-memory) | Load filtered rows, build CSV, return | Auto ✓ |
| Streaming | StreamingResponse with row-by-row yield | |

**Decision:** Batch for v1 (<10k users expected). CSV injection protection via single-quote prefix on dangerous cell starts. Money as plain strings, timestamps ISO 8601 UTC. Same filter params as list endpoints.

---

## Audit Log Viewer UX

| Option | Description | Selected |
|--------|-------------|----------|
| Expandable JSON payload | Collapsed preview + click to expand full JSON | Auto ✓ |
| Parsed/structured payload | Custom renderers per event_type | |

**Decision:** Raw JSON with expand/collapse. Hardcoded event_type dropdown for filters. No edit affordance. Paginated with 50-row default page size.

---

## Claude's Discretion

- Migration naming (may not need new migration — `banned_at` already exists)
- Test organization (`backend/tests/admin/`)
- Frontend page structure (Next.js App Router conventions)
- DataTable column widths and responsive behavior
- CSV column ordering and header naming
- Error message wording for banned user actions

## Deferred Ideas

- Admin frontend for markets CRUD (backend exists from Phase 4)
- Bulk actions on user list
- Admin notification system for critical events
- User profile self-editing by players
