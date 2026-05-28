# Phase 8: Admin CRM (User Management & Audit Log Viewer) - Research

**Researched:** 2026-05-28
**Domain:** Admin CRUD UI (FastAPI backend + Next.js 15 frontend), ban/unban state machine, CSV export, audit log viewer
**Confidence:** HIGH

## Summary

Phase 8 builds the operator's CRM surface: a paginated user list with search/filters, a user detail page with tabbed profile/wallet/bets views, ban/unban state machine with frozen-balance semantics, CSV export with injection protection, and an immutable audit log viewer. The phase spans both backend (new API endpoints, ban enforcement) and frontend (3 new admin pages with TanStack Table v8 + shadcn DataTable).

The codebase is well-prepared: `User.banned_at` column already exists (Phase 2 D-10), `AuditService.record()` is the single audit writer (Phase 1), `WalletService.get_balance()` / `.get_transactions()` are shipped (Phase 3), the `PaginatedResponse[T]` generic is established (Phase 4 `markets/schemas.py`), and the `current_active_admin` dependency gates all admin endpoints. The admin layout (Phase 2) has placeholder nav links ready for Phase 8 to activate.

No new database migrations are needed unless indexing `users.banned_at` for list filtering performance is desired. The `banned_at` column, audit_log table, and all wallet/bet models already exist. The phase is purely additive: new API routes, ban enforcement logic inserted at 3 points, new frontend pages.

**Primary recommendation:** Build backend API first (user list, detail aggregation, ban/unban, CSV export, audit log read), then layer frontend pages on top. Ban enforcement (login check, bet placement check, recharge check) is the highest-risk area -- test all 3 enforcement points with negative tests before touching the frontend.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01: `banned_at` timestamp as ban signal** -- `User.banned_at` column already exists. Ban = `banned_at IS NOT NULL`. No separate status enum.
- **D-02: Ban enforcement points** -- Three layers: (1) Login 403, (2) Bet placement check, (3) Admin recharge check. All return "Account suspended".
- **D-03: Frozen balance semantics** -- Wallet balance visible but immutable when banned. No zeroing, no escrow.
- **D-04: Ban/unban audit events** -- `admin.user_banned` and `admin.user_unbanned` with `{target_user_id, reason}`. Ban reason mandatory, unban reason optional.
- **D-05: Server-side pagination, search, filtering** -- Offset-limit `?page=1&page_size=20`. ILIKE on email/display_name. Filters: status, signup date range, has_activity_since. Server-side ORDER BY.
- **D-06: TanStack Table v8 + shadcn DataTable** -- Frontend columns: email, display name, status badge, signup date, last activity, wallet balance. Inline "View" link.
- **D-07: User detail page layout** -- Tabs: Profile (+ ban/unban), Wallet (balance + recharge + tx history), Bets (all bets). Each tab paginated. Recharge calls existing `POST /admin/wallets/{user_id}/recharge`.
- **D-08: Dedicated export endpoints** -- `GET /api/v1/admin/export/users`, `/export/transactions`, `/export/bets`. Admin-Bearer-gated. Same filter params as list endpoints. `text/csv` + `Content-Disposition: attachment`.
- **D-09: CSV injection protection** -- Cells beginning with `=`, `+`, `-`, `@`, `\t`, `\r` prefixed with `'`. Money as plain strings. Timestamps ISO 8601 UTC.
- **D-10: Batch CSV (not streaming)** -- Load all filtered rows, write CSV in memory. Streaming deferred.
- **D-11: Audit log read-only paginated view** -- `GET /api/v1/admin/audit-log`. Filters: event_type dropdown, actor free text, date range. No edit/delete affordance.
- **D-12: JSONB payload display** -- Collapsible JSON block, collapsed by default (80-char preview). Raw JSON in v1.
- **D-13: Known event types** -- Hardcoded dropdown list from Phases 1-7 (19 event types + 2 new from Phase 8).

### Claude's Discretion
- Migration naming (may not need one if ban logic is purely application-level)
- Backend test organization: `backend/tests/admin/` directory
- Frontend page structure following Next.js App Router conventions
- DataTable column width ratios and responsive behavior
- Audit log page size (default 50)
- CSV column ordering and header naming
- Error message wording for banned user actions

### Deferred Ideas (OUT OF SCOPE)
- Admin frontend for markets CRUD visual
- Bulk actions on user list
- Admin notification system
- User profile editing by users themselves
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ADU-01 | Admin can view paginated user list with search and filters | D-05 server-side pagination + TanStack Table pattern; existing `PaginatedResponse[T]` from Phase 4 |
| ADU-02 | Admin can open user detail page (profile, wallet, transactions, bets, ban status) | D-07 tabs layout; `WalletService.get_balance()` + `.get_transactions()` already shipped; `Bet` model queryable by `user_id` |
| ADU-04 | Admin can ban a user (state machine, login blocked, bets rejected, balance frozen) | D-01 `banned_at`, D-02 three enforcement points, D-03 frozen semantics, D-04 audit events |
| ADU-05 | Admin can unban a user; balance restored as-is | D-01 `banned_at = None`, D-03 balance unchanged, D-04 `admin.user_unbanned` audit event |
| ADU-06 | Admin can export users/transactions/bets to CSV | D-08 dedicated endpoints, D-09 injection protection, D-10 batch approach |
| ADD-04 | Admin can view audit log (chronological, filterable, immutable, read-only) | D-11 paginated endpoint, D-12 JSONB display, D-13 event type dropdown |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| User list (search, filter, sort, paginate) | API / Backend | Frontend Server (SSR) | Server-side ILIKE + ORDER BY + OFFSET/LIMIT; frontend renders TanStack Table |
| User detail aggregation | API / Backend | -- | Single endpoint aggregates user + balance + transaction count + bet count |
| Ban/unban state machine | API / Backend | -- | `banned_at` write + 3 enforcement points are purely backend; frontend calls API |
| Ban enforcement at login | API / Backend | -- | `UserManager.on_after_login` or dependency; must be server-side |
| Ban enforcement at bet placement | API / Backend | -- | Existing `current_betting_player` already checks `banned_at` (shipped in Phase 5) |
| Ban enforcement at recharge | API / Backend | -- | New check in `recharge_wallet` endpoint handler |
| CSV export | API / Backend | -- | CSV generation in Python with `csv.writer` + `io.StringIO`; returned as `Response` |
| Audit log read | API / Backend | -- | Query `audit_log` table with filters; return paginated JSON |
| Admin pages UI | Frontend Server (SSR) | Browser / Client | Next.js App Router pages + client-side TanStack Table state management |
| JSONB payload expand/collapse | Browser / Client | -- | Pure client-side toggle; no API call |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.115.x | Backend API framework | Already locked in pyproject.toml [VERIFIED: pyproject.toml] |
| SQLAlchemy 2.0 | 2.0.43+ | ORM for user queries, audit log reads | Already locked [VERIFIED: pyproject.toml] |
| Next.js 15 | 15.5.18 | Frontend framework (App Router) | Already locked [VERIFIED: package.json -- note: package.json says ^16.2.6 but CONTEXT/STATE says 15.x pinned; the planner should verify which version is actually installed] |
| @tanstack/react-table | 8.21.3 | Headless table logic (pagination, sorting, filtering state) | D-06 locked decision [VERIFIED: npm registry, github.com/TanStack/table] |
| shadcn/ui | latest | UI primitives (Table, Tabs, Dialog, etc.) | Already established in Phase 2/6 [VERIFIED: existing components in frontend/src/components/ui/] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| sonner | 2.0.7 | Toast notifications for action confirmations | Already specified in UI-SPEC for recharge/ban feedback [VERIFIED: npm registry, github.com/emilkowalski/sonner] |
| Python csv module | stdlib | CSV generation | Built-in, no external dep needed [VERIFIED: Python stdlib] |
| Python io.StringIO | stdlib | In-memory CSV buffer | Built-in [VERIFIED: Python stdlib] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Python csv stdlib | pandas to_csv | pandas is a 30MB dep for a trivial CSV writer; stdlib csv is sufficient for <10k rows |
| Batch CSV (D-10) | StreamingResponse | Streaming adds complexity; batch is fine for v1 user counts (<10k) |
| TanStack Table | AG Grid | AG Grid is heavier; TanStack is headless and pairs with shadcn |

**Installation:**
```bash
# Frontend -- new dependencies
cd frontend && pnpm add @tanstack/react-table

# shadcn components (UI-SPEC specified)
pnpm dlx shadcn@latest add table tabs dialog dropdown-menu select textarea separator tooltip sonner
```

**Version verification:**
- `@tanstack/react-table`: 8.21.3 (last published 2026-05-19) [VERIFIED: npm registry]
- `sonner`: 2.0.7 (published 2025-08-02) [VERIFIED: npm registry]

No new backend Python dependencies needed -- all required libraries (FastAPI, SQLAlchemy, csv stdlib) are already installed.

## Package Legitimacy Audit

> slopcheck was unavailable at research time. All packages are tagged `[ASSUMED]` and the planner must gate each install behind a `checkpoint:human-verify` task.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| @tanstack/react-table | npm | 4+ yrs | very high | github.com/TanStack/table | N/A | [ASSUMED] -- well-known TanStack project, D-06 locked |
| sonner | npm | 3+ yrs | high | github.com/emilkowalski/sonner | N/A | [ASSUMED] -- UI-SPEC specifies it; shadcn officially integrates it |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*slopcheck was unavailable at research time. Both packages above are `[ASSUMED]`. The planner must gate install behind a `checkpoint:human-verify` task. However, both are D-06 locked decisions or UI-SPEC specified, and both have well-known GitHub repos with high star counts.*

## Architecture Patterns

### System Architecture Diagram

```
Admin Browser
    |
    v
[Next.js Edge Middleware] -- verifies admin_jwt cookie (jose HS256)
    |
    v
[Next.js App Router pages]
    |  - /admin/users (list)
    |  - /admin/users/[id] (detail)
    |  - /admin/audit-log (viewer)
    |
    v (client-side fetch with Bearer JWT)
[FastAPI API Layer]
    |
    +-- GET /api/v1/admin/users?page=&search=&status=&...
    |     -> SQLAlchemy query on `users` table (ILIKE, filters, ORDER BY, OFFSET/LIMIT)
    |     -> Joins to `accounts` for balance, aggregates from `bets`
    |
    +-- GET /api/v1/admin/users/{user_id}
    |     -> User profile + wallet balance + tx count + bet count
    |
    +-- POST /api/v1/admin/users/{user_id}/ban
    |     -> Sets banned_at = now(), audits admin.user_banned
    |
    +-- POST /api/v1/admin/users/{user_id}/unban
    |     -> Sets banned_at = None, audits admin.user_unbanned
    |
    +-- GET /api/v1/admin/users/{user_id}/transactions?page=&page_size=
    |     -> WalletService.get_transactions() (existing)
    |
    +-- GET /api/v1/admin/users/{user_id}/bets?page=&page_size=
    |     -> Query bets table by user_id (paginated)
    |
    +-- GET /api/v1/admin/export/users (CSV)
    +-- GET /api/v1/admin/export/transactions (CSV)
    +-- GET /api/v1/admin/export/bets (CSV)
    |     -> Same filters as list; csv.writer to StringIO; Response(media_type="text/csv")
    |
    +-- GET /api/v1/admin/audit-log?page=&event_type=&actor=&date_from=&date_to=
    |     -> Query audit_log table (ILIKE on actor, filter on event_type, date range)
    |
    +-- [BAN ENFORCEMENT] -- injected at 3 points:
          (1) Login: check banned_at in UserManager.on_after_login or a dependency
          (2) Bet placement: already done in current_betting_player (Phase 5)
          (3) Recharge: new check in recharge_wallet endpoint
```

### Recommended Project Structure

```
backend/app/admin/
    __init__.py          # (already exists, empty)
    router.py            # NEW: admin CRM router (user list, detail, ban, unban, bets)
    schemas.py           # NEW: UserListItem, UserDetail, BanRequest, etc.
    service.py           # NEW: AdminUserService (queries, ban/unban logic)
    csv_export.py        # NEW: CSV generation + injection protection

backend/app/core/audit/
    router.py            # NEW: admin audit log read endpoint

backend/tests/admin/
    __init__.py
    test_user_list.py
    test_user_detail.py
    test_ban_unban.py
    test_csv_export.py
    test_audit_log.py
    test_auth_negative.py

frontend/src/app/admin/
    users/
        page.tsx             # User list page
        [id]/
            page.tsx         # User detail page
    audit-log/
        page.tsx             # Audit log page

frontend/src/components/admin/
    users-data-table.tsx
    user-status-badge.tsx
    user-detail-tabs.tsx
    profile-tab.tsx
    wallet-tab.tsx
    bets-tab.tsx
    recharge-form.tsx
    ban-confirm-dialog.tsx
    unban-confirm-dialog.tsx
    audit-log-table.tsx
    audit-payload-viewer.tsx
    export-csv-button.tsx
    admin-search-input.tsx
    date-range-filter.tsx
    pagination-controls.tsx
```

### Pattern 1: Server-Side Paginated Admin Endpoint

**What:** All admin list endpoints use the same offset-limit pattern with typed query params.
**When to use:** Every list endpoint in this phase (users, transactions, bets, audit log).
**Example:**
```python
# Source: existing pattern from backend/app/markets/router.py + D-05
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from app.auth.deps import current_active_admin
from app.auth.models import User
from app.db.session import get_async_session

@router.get("/api/v1/admin/users", response_model=PaginatedResponse[UserListItem])
async def list_users(
    admin: Annotated[User, Depends(current_active_admin)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),  # "active" | "banned"
    signup_after: datetime | None = Query(default=None),
    signup_before: datetime | None = Query(default=None),
    sort_by: str = Query(default="created_at"),
    sort_order: str = Query(default="desc"),
) -> PaginatedResponse[UserListItem]:
    ...
```

### Pattern 2: TanStack Table with Server-Side State

**What:** TanStack Table v8 with manualPagination, manualSorting, manualFiltering.
**When to use:** All admin tables (user list, audit log, detail page sub-tables).
**Example:**
```typescript
// Source: TanStack Table v8 official docs (tanstack.com/table/v8/docs/guide/pagination)
"use client";

import { useReactTable, getCoreRowModel } from "@tanstack/react-table";

const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: 20 });
const [sorting, setSorting] = useState<SortingState>([]);

const table = useReactTable({
  columns,
  data: serverData.items,
  getCoreRowModel: getCoreRowModel(),
  manualPagination: true,
  manualSorting: true,
  rowCount: serverData.total,
  onPaginationChange: setPagination,
  onSortingChange: setSorting,
  state: { pagination, sorting },
});
```

### Pattern 3: CSV Injection Protection

**What:** Sanitize CSV cell values that start with formula-trigger characters.
**When to use:** All CSV export endpoints (D-09).
**Example:**
```python
# Source: OWASP CSV Injection prevention + D-09 spec
import csv
import io

FORMULA_TRIGGERS = {"=", "+", "-", "@", "\t", "\r"}

def sanitize_csv_cell(value: str) -> str:
    """Prefix formula-trigger characters with single quote (D-09)."""
    if value and value[0] in FORMULA_TRIGGERS:
        return f"'{value}"
    return value

def export_users_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["email", "display_name", "status", ...])
    writer.writeheader()
    for row in rows:
        writer.writerow({k: sanitize_csv_cell(str(v)) for k, v in row.items()})
    return buf.getvalue()
```

### Pattern 4: Ban/Unban Endpoint with Audit

**What:** Stateful ban toggle with mandatory reason audit trail.
**When to use:** POST /admin/users/{user_id}/ban and /unban endpoints.
**Example:**
```python
# Source: D-01 + D-02 + D-04 pattern
from datetime import UTC, datetime

async def ban_user(user_id: UUID, reason: str, admin: User, session: AsyncSession) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if user.banned_at is not None:
        raise HTTPException(409, "User is already banned")
    user.banned_at = datetime.now(UTC)
    await session.flush()
    await AuditService.record(
        session,
        actor=f"user:{admin.id}",
        event_type="admin.user_banned",
        payload={"target_user_id": str(user_id), "reason": reason},
        ip=ip,
    )
    await session.commit()
    return user
```

### Pattern 5: Admin API Fetch from Frontend

**What:** Client-side fetch with Bearer JWT from admin_jwt cookie.
**When to use:** All frontend admin pages fetching data.
**Example:**
```typescript
// Source: existing adminLoginAction pattern from frontend/src/lib/auth.ts
"use client";

async function fetchAdminApi(path: string, opts?: RequestInit) {
  // The admin_jwt cookie is HttpOnly and scoped to /admin -- we cannot read it
  // client-side. Admin API calls must go through a Server Action or Route Handler
  // that reads the cookie and forwards it as a Bearer header.
  const res = await fetch(path, {
    ...opts,
    credentials: "include",
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}
```

**IMPORTANT NOTE on admin Bearer forwarding:** The admin JWT is stored as an HttpOnly cookie scoped to `/admin`. Client Components cannot read it directly. The frontend must either:
1. Use Next.js Server Actions that read `cookies().get("admin_jwt")` and forward as `Authorization: Bearer` header to FastAPI, OR
2. Use a Next.js Route Handler (API route) as a proxy that reads the cookie and forwards the request.

The existing pattern from Phase 2 (`adminLoginAction` in `auth.ts`) stores the token in `admin_jwt` cookie. Phase 8 pages will need a helper function to extract and forward this token.

### Anti-Patterns to Avoid
- **Client-side filtering/sorting on paginated data:** With server-side pagination, sorting/filtering only the visible page is useless. All three must be server-side (D-05).
- **Mutating wallet balance during ban:** D-03 explicitly forbids zeroing or modifying balance. The freeze is purely enforcement-layer (reject writes), not data-layer.
- **Editing audit log entries:** D-11 says read-only. No PUT/PATCH/DELETE on audit_log. The Phase 1 DB trigger + REVOKE already blocks this at Postgres level.
- **Missing `from __future__ import annotations` constraint:** Router files on Python 3.13 must NOT use `from __future__ import annotations` (existing project constraint -- FastAPI dependency resolution breaks). New router files must follow this.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CSV generation | Custom string concatenation | Python `csv.DictWriter` + `io.StringIO` | Handles quoting, escaping, newlines correctly |
| CSV injection protection | Regex-based sanitizer | Simple prefix check + `'` prepend (D-09) | OWASP-recommended; `=+-.@\t\r` are the exhaustive trigger set |
| Table sorting/pagination state | Custom useState hooks | TanStack Table `useReactTable` with `manualPagination`/`manualSorting` | Handles all edge cases (page bounds, sort direction toggle, state sync) |
| Toast notifications | Custom toast component | sonner (shadcn wraps it) | Accessible, animated, de-duplication built in |
| Confirmation dialogs | Custom modal | Radix Dialog via shadcn `Dialog` | Focus trap, Escape key, aria attributes, overlay click |

**Key insight:** The heaviest custom code in this phase is the backend query layer (user list with joins to wallet balance + last activity). The frontend is almost entirely assembly of existing primitives (TanStack + shadcn). The ban enforcement is the riskiest custom code -- it touches 3 separate code paths and needs negative tests at all 3.

## Common Pitfalls

### Pitfall 1: Ban Enforcement Gaps
**What goes wrong:** Banning sets `banned_at` but one of the 3 enforcement points is missed, allowing the banned user to still log in, place bets, or receive recharges.
**Why it happens:** Enforcement is distributed across 3 different code paths (login, bet, recharge) with no centralized middleware.
**How to avoid:** Write a negative integration test for each enforcement point BEFORE implementing. The bet enforcement already exists in `current_betting_player` (Phase 5 `bets/router.py` line 58). Login and recharge enforcement are new.
**Warning signs:** A banned user can still perform any action.

### Pitfall 2: Admin Bearer Forwarding from Next.js Client Components
**What goes wrong:** Client Components try to read the `admin_jwt` HttpOnly cookie directly, which is impossible from JavaScript. API calls fail with 401.
**Why it happens:** The admin JWT is stored as an HttpOnly cookie (correct for security) but Client Components need to call the FastAPI admin API with `Authorization: Bearer`.
**How to avoid:** Use Server Actions or Next.js Route Handlers as a proxy layer. The Server Action reads `cookies().get("admin_jwt")` and forwards as Bearer to FastAPI. Alternatively, if client-side fetch is needed (e.g., for TanStack Table refetching), create a Next.js API Route at `/app/admin/api/[...path]/route.ts` that proxies requests.
**Warning signs:** 401 errors on admin page loads despite being logged in.

### Pitfall 3: ILIKE Injection on Search
**What goes wrong:** User-supplied search string contains `%` or `_` wildcards, causing unintended pattern matches.
**Why it happens:** ILIKE treats `%` and `_` as wildcards. A search for `100%` would match any string containing `100` followed by anything.
**How to avoid:** Escape `%` and `_` in the search parameter before passing to ILIKE. SQLAlchemy's `col.ilike(f"%{escaped}%")` with manual escaping of the input string.
**Warning signs:** Search results include unexpected matches.

### Pitfall 4: N+1 Queries on User List with Balance
**What goes wrong:** The user list endpoint queries users, then loops to fetch each user's wallet balance individually, causing O(n) queries per page.
**Why it happens:** Balance lives in the `accounts` table, not `users`. A naive implementation queries users then calls `WalletService.get_balance()` per user.
**How to avoid:** Use a single SQL query with a LEFT JOIN or subquery to fetch `accounts.balance` alongside user columns. The join condition is `accounts.owner_id = users.id AND accounts.kind = 'user_wallet'`.
**Warning signs:** User list endpoint >500ms for 20 rows.

### Pitfall 5: CSV Export Memory on Large Datasets
**What goes wrong:** Exporting 10k+ rows loads all data into memory, causing slow response or OOM.
**Why it happens:** D-10 specifies batch (not streaming) for v1.
**How to avoid:** For v1, batch is acceptable (<10k users expected). Add a server-side LIMIT (e.g., 10000) on export queries to prevent unbounded memory usage. Log a warning if the limit is hit.
**Warning signs:** Export endpoint times out or returns 502.

### Pitfall 6: MissingGreenlet on Admin ORM Instance After Session Commit
**What goes wrong:** After committing the ban/unban update, accessing `user.email` or `user.id` triggers a lazy reload outside the async greenlet, causing `MissingGreenlet`.
**Why it happens:** SQLAlchemy 2.0 async sessions expire instances after commit. Accessing expired attributes triggers sync IO.
**How to avoid:** Capture plain values (`user_id = user.id`, `email = user.email`) BEFORE the commit, or use `expire_on_commit=False` on the session. The existing `recharge_wallet` endpoint (Phase 3 `wallet/admin_router.py` line 75) demonstrates this exact pattern.
**Warning signs:** `MissingGreenlet: greenlet_spawn has not been called` errors.

### Pitfall 7: `from __future__ import annotations` in New Router Files
**What goes wrong:** Adding `from __future__ import annotations` to a new router file causes FastAPI to mis-resolve `Annotated[T, Depends(...)]` parameters as query params, returning 422 on valid requests.
**Why it happens:** Python 3.13 + FastAPI's `inspect.signature` dependency resolver breaks when annotations are forward-ref strings. This is documented in multiple existing router files.
**How to avoid:** Do NOT add `from __future__ import annotations` to `admin/router.py` or `core/audit/router.py`. Import types at runtime. Follow the existing pattern from `wallet/admin_router.py`, `bets/router.py`.
**Warning signs:** 422 Unprocessable Entity on requests that should be valid.

## Code Examples

### Ban Enforcement at Login

```python
# Source: D-02 enforcement point (1) + existing on_after_login pattern from
# fastapi-users UserManager
# Location: backend/app/auth/manager.py (extend existing UserManager)

async def on_after_login(
    self,
    user: User,
    request: Request | None = None,
    response: Response | None = None,
) -> None:
    """Phase 8 ban check: reject login for banned users with 403."""
    if user.banned_at is not None:
        # Revoke the just-minted token so it cannot be used
        # (the strategy already wrote it; we must destroy it)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account suspended",
        )
```

**Note:** `on_after_login` fires AFTER the token is minted. For a cleaner approach, consider a custom `on_after_login` hook that checks `banned_at` before the response is sent, or add the check as a FastAPI dependency that runs after authentication but before the response. The exact implementation depends on how fastapi-users v15 handles the hook timing -- the planner should verify whether the token must be revoked or if blocking the response is sufficient.

### CSV Export Endpoint

```python
# Source: D-08 + D-09 + D-10 pattern
from fastapi import Response

@router.get("/api/v1/admin/export/users")
async def export_users_csv(
    admin: Annotated[User, Depends(current_active_admin)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    status: str | None = Query(default=None),
    # ... same filter params as list_users
) -> Response:
    rows = await AdminUserService.get_filtered_users(session, status=status, ...)
    csv_content = build_csv(rows, columns=["email", "display_name", ...])
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=users.csv"},
    )
```

### Audit Log Read Endpoint

```python
# Source: D-11 + D-13 pattern
@router.get("/api/v1/admin/audit-log", response_model=PaginatedResponse[AuditLogItem])
async def list_audit_log(
    admin: Annotated[User, Depends(current_active_admin)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    event_type: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
) -> PaginatedResponse[AuditLogItem]:
    query = select(AuditLog).order_by(AuditLog.occurred_at.desc())
    if event_type:
        query = query.where(AuditLog.event_type == event_type)
    if actor:
        query = query.where(AuditLog.actor.ilike(f"%{escape_like(actor)}%"))
    if date_from:
        query = query.where(AuditLog.occurred_at >= date_from)
    if date_to:
        query = query.where(AuditLog.occurred_at <= date_to)
    # ... count + offset/limit pagination
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| react-table v7 (class-based) | TanStack Table v8 (headless, hooks-based) | 2022 | v8 is fully headless; column defs are type-safe; works with any UI library |
| Custom CSV sanitization | OWASP-recommended prefix approach | Ongoing | Single-quote prefix for `=+-.@\t\r` is the standard defense |
| Client-side table filtering | Server-side with manualPagination | Always for paginated data | Client-side filtering only works on the current page, not the full dataset |

**Deprecated/outdated:**
- react-table v7: Replaced by TanStack Table v8. Different API entirely (hooks vs render props).
- `useTable` hook: v7 API. v8 uses `useReactTable`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Next.js version is 15.x despite package.json showing ^16.2.6 | Standard Stack | If actually 16.x, some patterns (cookies(), middleware) may differ. CONTEXT and STATE both reference 15.x. Planner should verify actual installed version. |
| A2 | `on_after_login` hook in fastapi-users v15 fires after token mint but before response send | Code Examples (ban at login) | If the hook fires after the response is already sent, the ban check arrives too late. May need an alternative approach (dependency check). |
| A3 | TanStack Table v8.21.3 is compatible with React 19 | Standard Stack | React 19 is the project's React version. TanStack Table v8 should be compatible but was not verified against React 19 specifically. |

## Open Questions

1. **Next.js version discrepancy**
   - What we know: `package.json` shows `"next": "^16.2.6"` but multiple CONTEXT/STATE entries reference Next 15.x and the decision to pin `next@^15.5.18`. The current `frontend/node_modules` glob suggests 15.5.18 is installed.
   - What's unclear: Whether `package.json` was updated to ^16 after Phase 2's pin decision.
   - Recommendation: The planner should run `pnpm list next` in `frontend/` to confirm the installed version before planning frontend tasks.

2. **Ban enforcement at login -- hook vs dependency**
   - What we know: D-02 says "UserManager.on_after_login or a dependency check". fastapi-users v15 `on_after_login` fires after successful auth.
   - What's unclear: Whether `on_after_login` can raise an HTTP exception to block the response, or whether a separate dependency is cleaner.
   - Recommendation: Test in the plan's first wave. A separate FastAPI dependency (`current_unbanned_player`) that wraps `current_active_player` + checks `banned_at` is the safest approach. However, for the admin login path, the check must happen in the admin login proxy function (`admin_login_proxy` in `admin_router.py` line 149) since admin users cannot be banned in v1 (they're superusers).

3. **Admin API proxy architecture for frontend**
   - What we know: Admin JWT is HttpOnly cookie scoped to `/admin`. Client Components cannot read it.
   - What's unclear: Whether to use Server Actions (existing pattern), Route Handlers (new `/app/admin/api/` proxy), or have the Next.js Server Components do SSR data fetching.
   - Recommendation: Use Next.js Server Components for initial data fetch (SSR reads cookie, forwards Bearer, returns data to page). For client-side pagination/sorting (TanStack Table state changes), use a thin Route Handler proxy or Server Actions for refetch.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | Frontend build | Yes | 25.2.1 | -- |
| pnpm | Package management | Yes | 9.15.0 | -- |
| Python 3.13 | Backend | Yes | 3.13.7 | -- |
| PostgreSQL | Data storage | Yes (via Docker) | 16 | -- |
| Redis | Rate limiting | Yes (via Docker) | 7 | -- |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio 0.25 (backend), Vitest 2.1.9 (frontend) |
| Config file | `backend/pyproject.toml` [tool.pytest.ini_options], `frontend/vitest.config.ts` |
| Quick run command | `cd backend && uv run pytest tests/admin/ -x -q` |
| Full suite command | `cd backend && uv run pytest -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ADU-01 | Paginated user list with search/filters | integration | `uv run pytest tests/admin/test_user_list.py -x` | No -- Wave 0 |
| ADU-02 | User detail (profile, wallet, bets) | integration | `uv run pytest tests/admin/test_user_detail.py -x` | No -- Wave 0 |
| ADU-04 | Ban user + 3 enforcement points | integration | `uv run pytest tests/admin/test_ban_unban.py -x` | No -- Wave 0 |
| ADU-05 | Unban user + balance restored | integration | `uv run pytest tests/admin/test_ban_unban.py -x` | No -- Wave 0 |
| ADU-06 | CSV export with injection protection | integration | `uv run pytest tests/admin/test_csv_export.py -x` | No -- Wave 0 |
| ADD-04 | Audit log viewer (read-only, filterable) | integration | `uv run pytest tests/admin/test_audit_log.py -x` | No -- Wave 0 |
| -- | Negative auth: all /admin/* require is_admin | integration | `uv run pytest tests/admin/test_auth_negative.py -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && uv run pytest tests/admin/ -x -q`
- **Per wave merge:** `cd backend && uv run pytest -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/admin/__init__.py` -- new test directory
- [ ] `backend/tests/admin/conftest.py` -- shared fixtures (seeded admin user, seeded player, seeded banned user)
- [ ] `backend/tests/admin/test_user_list.py` -- ADU-01
- [ ] `backend/tests/admin/test_user_detail.py` -- ADU-02
- [ ] `backend/tests/admin/test_ban_unban.py` -- ADU-04, ADU-05
- [ ] `backend/tests/admin/test_csv_export.py` -- ADU-06
- [ ] `backend/tests/admin/test_audit_log.py` -- ADD-04
- [ ] `backend/tests/admin/test_auth_negative.py` -- SC#6 negative auth

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `current_active_admin` dependency on all endpoints (existing from Phase 2) |
| V3 Session Management | yes | Admin Bearer JWT with 15-min expiry (existing); ban enforcement blocks stale sessions |
| V4 Access Control | yes | `is_superuser=True` enforced by `current_active_admin`; player cookie returns 403 on /admin/* |
| V5 Input Validation | yes | Pydantic schemas (`extra="forbid"` on write endpoints); ILIKE escape on search; CSV injection sanitization |
| V6 Cryptography | no | No new crypto operations in this phase |

### Known Threat Patterns for this Phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| CSV injection (formula execution in Excel) | Tampering | D-09: prefix formula-trigger chars with `'` |
| ILIKE wildcard injection | Information Disclosure | Escape `%` and `_` in search input before ILIKE |
| Ban bypass via stale session | Elevation of Privilege | Check `banned_at` on EVERY protected action (login, bet, recharge), not just at session start |
| Unauthorized admin access (player cookie on /admin/*) | Elevation of Privilege | SC#6 negative test: player cookie returns 403 on all new /admin/* endpoints |
| IDOR on user detail | Information Disclosure | `current_active_admin` dependency ensures only admins can access /admin/users/{id}; no player path exists |

## Project Constraints (from CLAUDE.md)

- **Phase branch workflow:** Work on `gsd/phase-8-admin-crm-user-management-audit-log-viewer` branch, never on main.
- **PHASES.md tracking:** AI must update PHASES.md before touching code (mark "In progress") and when opening PR (mark "In review").
- **Subagent parallelism:** Use subagents for independent tasks; reserve inline for sequential/shared-state.
- **No `from __future__ import annotations` in router files** (Python 3.13 + FastAPI constraint).
- **`current_active_admin`** dependency is the auth gate for all admin endpoints.
- **Money serialization:** All Decimal values as strings in JSON responses (`MoneyStr` pattern from Phase 3).
- **Audit via `AuditService.record()`** only -- no raw INSERT INTO audit_log.
- **structlog** for all backend logging.
- **`tenant_id` ghost column** on any new table (none expected in this phase).
- **Admin is `is_admin` boolean (`is_superuser`) in v1** -- no RBAC.
- **Spanish for conversation, English for code/paths.**

## Sources

### Primary (HIGH confidence)
- `backend/app/auth/models.py` -- User model with `banned_at` column [VERIFIED: codebase]
- `backend/app/auth/deps.py` -- `current_active_admin` dependency [VERIFIED: codebase]
- `backend/app/core/audit/service.py` -- `AuditService.record()` signature [VERIFIED: codebase]
- `backend/app/core/audit/models.py` -- `AuditLog` ORM model [VERIFIED: codebase]
- `backend/app/wallet/service.py` -- `WalletService.get_balance()`, `.get_transactions()` [VERIFIED: codebase]
- `backend/app/wallet/admin_router.py` -- Recharge endpoint pattern [VERIFIED: codebase]
- `backend/app/markets/schemas.py` -- `PaginatedResponse[T]` generic pattern [VERIFIED: codebase]
- `backend/app/markets/router.py` -- Admin list endpoint pagination pattern [VERIFIED: codebase]
- `backend/app/bets/router.py` -- `current_betting_player` with `banned_at` check [VERIFIED: codebase]
- `frontend/src/app/admin/layout.tsx` -- Admin layout with placeholder nav [VERIFIED: codebase]
- `frontend/src/lib/auth.ts` -- `adminLoginAction` + Bearer cookie pattern [VERIFIED: codebase]
- `.planning/phases/08-admin-crm-user-management-audit-log-viewer/08-CONTEXT.md` -- D-01 through D-13 [VERIFIED: codebase]
- `.planning/phases/08-admin-crm-user-management-audit-log-viewer/08-UI-SPEC.md` -- Full UI design contract [VERIFIED: codebase]

### Secondary (MEDIUM confidence)
- [TanStack Table v8 Pagination Guide](https://tanstack.com/table/v8/docs/guide/pagination) -- `manualPagination`, `rowCount`, `onPaginationChange` [CITED: tanstack.com]
- [TanStack Table v8 Sorting Guide](https://tanstack.com/table/v8/docs/guide/sorting) -- `manualSorting` [CITED: tanstack.com]
- npm registry: `@tanstack/react-table@8.21.3` confirmed [VERIFIED: npm view]
- npm registry: `sonner@2.0.7` confirmed [VERIFIED: npm view]

### Tertiary (LOW confidence)
- CSV injection prevention (OWASP pattern) -- standard practice but not verified against a specific OWASP URL in this session [ASSUMED]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries are either already installed or well-known with locked decisions
- Architecture: HIGH -- all patterns are direct extensions of existing Phase 2-6 code; no new architectural decisions
- Pitfalls: HIGH -- all 7 pitfalls derive from verified codebase patterns and known SQLAlchemy/FastAPI behaviors

**Research date:** 2026-05-28
**Valid until:** 2026-06-28 (stable domain; no fast-moving external dependencies)
