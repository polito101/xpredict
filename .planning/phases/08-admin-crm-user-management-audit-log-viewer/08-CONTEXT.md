# Phase 8: Admin CRM (User Management & Audit Log Viewer) - Context

**Gathered:** 2026-05-28
**Status:** Ready for planning

<domain>
## Phase Boundary

**Build the operator's CRM surface in the admin UI: paginated user list with search/filters, user detail page (profile + balance + transaction history + bets + ban status), ban/unban state machine with frozen-balance semantics, inline recharge (calling Phase 3 primitive), CSV export of users/transactions/bets, and an immutable audit log viewer — the "I can manage my customers" demo surface.**

Phase 8 delivers ADU-01, ADU-02, ADU-04, ADU-05, ADU-06, ADD-04:

- Backend API: paginated user list with search + filters, user detail aggregation endpoint, ban/unban endpoints, CSV export endpoints, audit log read endpoint
- Frontend admin pages: `/admin/users` (list), `/admin/users/{id}` (detail with recharge form), `/admin/audit-log` (viewer)
- Ban/unban state machine enforced at API level (login blocked, bets rejected, recharges rejected for banned users)
- CSV export with injection protection
- Audit log viewer: read-only, filterable, paginated

**Out of this phase entirely:**
- Admin KPI dashboard (landing page) -> Phase 10
- Configurable branding -> Phase 10
- Player-facing UI changes -> Phase 9
- Market management admin UI (backend API exists from Phase 4) -> already done at API level; admin frontend for markets is Phase 10 or deferred
- User profile editing by users themselves -> future
- Admin role management / RBAC -> v2

</domain>

<decisions>
## Implementation Decisions

### Ban/Unban State Machine
- **D-01: `banned_at` timestamp as ban signal** — `User.banned_at` column already exists (Phase 2, D-10). A user is banned when `banned_at IS NOT NULL`. Ban sets `banned_at = now()`, unban sets `banned_at = None`. No separate `status` enum needed — the nullable timestamp doubles as state + audit trail of when the ban happened.
- **D-02: Ban enforcement points** — Three enforcement layers: (1) Login: `UserManager.on_after_login` or a dependency check rejects banned users with 403 (not 401 — the credentials are valid, the account is suspended); (2) Bet placement: the bet endpoint checks `banned_at` before accepting; (3) Admin recharge: the recharge endpoint checks `banned_at` before crediting. All three return a clear error message ("Account suspended").
- **D-03: Frozen balance semantics** — When banned, the wallet balance is visible (GET /wallet/me/balance still works if the user has an existing session) but immutable: no bets, no recharges, no outflows. The balance value is never modified during ban/unban — it persists exactly as-is. No silent zeroing, no escrow transfer.
- **D-04: Ban/unban audit events** — `admin.user_banned` and `admin.user_unbanned` audit events with payload `{target_user_id, reason}`. The admin must provide a mandatory reason text when banning (not when unbanning — unban reason is optional).

### Admin Table Design
- **D-05: Server-side pagination, search, and filtering** — All list endpoints use server-side offset-limit pagination (existing `?page=1&page_size=20` pattern). Search is server-side ILIKE on `email` and `display_name`. Filters: `status` (active/banned), `signup_after`/`signup_before` date range, `has_activity_since` (last bet/login timestamp). Sort by any visible column (server-side ORDER BY).
- **D-06: TanStack Table v8 + shadcn DataTable** — Frontend uses TanStack Table for column definitions, sorting state, and pagination state. shadcn/ui DataTable component wraps it. Columns: email, display name, status badge (active/banned), signup date, last activity, wallet balance. Inline actions column with "View" link to detail page.
- **D-07: User detail page layout** — Tabs: "Profile" (fields + ban/unban button), "Wallet" (balance + recharge form + transaction history table), "Bets" (all bets table with market, outcome, stake, status, P&L). Each tab has its own paginated table. Recharge form calls existing `POST /admin/wallets/{user_id}/recharge` endpoint (Phase 3 primitive).

### CSV Export
- **D-08: Dedicated export endpoints** — `GET /api/v1/admin/export/users`, `/export/transactions`, `/export/bets`. Admin-Bearer-gated. Accept the same filter query params as the list endpoints (so the admin can export the current filtered view). Response is `text/csv` with `Content-Disposition: attachment`.
- **D-09: CSV injection protection** — Cells beginning with `=`, `+`, `-`, `@`, `\t`, `\r` are prefixed with a single quote `'` to prevent formula injection in Excel/Sheets. Money values exported as plain strings (no currency symbol, same `Decimal -> str` pattern as API responses). Timestamps in ISO 8601 UTC.
- **D-10: Streaming vs batch** — Batch (load all filtered rows, write CSV in memory, return). For v1 user counts (<10k expected), streaming is unnecessary complexity. If performance becomes an issue, switch to `StreamingResponse` with row-by-row yield — the endpoint contract stays the same.

### Audit Log Viewer
- **D-11: Read-only paginated view** — `GET /api/v1/admin/audit-log` returns paginated audit entries. Filters: `event_type` (dropdown of known types), `actor` (free text search on actor field), `date_from`/`date_to` range. No edit/delete affordance anywhere — the UI has no mutation controls, and the DB trigger + REVOKE from Phase 1 block any attempt.
- **D-12: JSONB payload display** — The `payload` column is rendered as an expandable/collapsible JSON block in each audit row. Collapsed by default showing a one-line preview (first key-value pair or truncated to 80 chars). Click to expand full formatted JSON. No parsing/prettifying of specific event types in v1 — raw JSON is sufficient for the operator demo.
- **D-13: Known event types for filter dropdown** — Hardcoded list of event types from Phases 1-7: `auth.player_registered`, `auth.login_started`, `auth.login_failed`, `auth.admin_login_started`, `auth.admin_login_failed`, `auth.session_revoked`, `auth.password_reset`, `auth.email_verified`, `wallet.recharge`, `wallet.reconciliation`, `bet.placed`, `market.created`, `market.updated`, `market.closed`, `market.resolved`, `settlement.completed`, `settlement.reversed`, `admin.user_banned`, `admin.user_unbanned`. New event types added in future phases extend this list.

### Claude's Discretion
- Migration naming: `0007_phase8_ban_enforcement.py` or appropriate sequence number (may not need a new migration if ban logic is purely application-level using existing `banned_at` column)
- Backend test organization: `backend/tests/admin/` directory for CRM-specific tests
- Frontend page structure: `/admin/users/page.tsx`, `/admin/users/[id]/page.tsx`, `/admin/audit-log/page.tsx` following Next.js App Router conventions
- DataTable column width ratios and responsive behavior
- Audit log pagination page size (default 50 — audit logs are typically inspected in detail)
- CSV column ordering and header naming conventions
- Error message wording for banned user actions

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` §Admin — User CRM (ADU-01..06) + §Admin — Dashboard & Branding (ADD-04)
- `.planning/ROADMAP.md` §Phase 8 — goal, 6 success criteria, pitfalls #6 and #8

### Prior Phase Context (foundations this phase builds on)
- `.planning/phases/02-auth-identity/02-CONTEXT.md` — Admin auth (Bearer JWT, `current_active_admin`, D-03 cross-surface isolation), User model with `banned_at` (D-10), Edge middleware pattern
- `.planning/phases/03-wallet-double-entry-ledger/03-CONTEXT.md` — WalletService API, recharge primitive, money-as-string serialization, pagination pattern

### Existing Code (critical to read)
- `backend/app/auth/admin_router.py` — Admin Bearer auth pattern, `current_active_admin` dependency, audit session pattern
- `backend/app/auth/models.py` — `User` model with `banned_at`, `display_name`, `token_version`, `is_superuser` columns
- `backend/app/wallet/admin_router.py` — Recharge endpoint pattern (Phase 3 primitive that Phase 8 UI calls)
- `backend/app/wallet/service.py` — `WalletService.recharge()`, `get_balance()`, `get_transactions()`
- `backend/app/core/audit/service.py` — `AuditService.record()` signature (the ONLY audit writer)
- `backend/app/core/audit/models.py` — `AuditLog` ORM model (actor, event_type, payload JSONB, ip, tenant_id)
- `backend/app/wallet/router.py` — Player wallet read surface pattern (GET /wallet/me/balance, /wallet/me/transactions)

### Project Constraints
- `.planning/PROJECT.md` §Constraints — Admin is `is_admin` boolean flag in v1; full RBAC in v2
- `.planning/PROJECT.md` §Key Decisions — "Timeline: sin presion de fecha. Hazlo bien."

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/auth/deps.py` — `current_active_admin` dependency for all `/admin/*` endpoints
- `app/wallet/admin_router.py` — Recharge endpoint pattern (Phase 8 detail page calls this)
- `app/wallet/service.py` — `WalletService.get_balance()`, `.get_transactions()` for user detail
- `app/core/audit/service.py` — `AuditService.record()` for ban/unban audit events
- `app/core/audit/models.py` — `AuditLog` model for the audit log viewer query
- `app/auth/models.py` — `User` model with `banned_at` already shipped
- `app/auth/rate_limit.py` — Rate limiting pattern (slowapi + Redis)
- `app/markets/router.py` — Existing offset-limit pagination pattern to reuse
- Frontend: shadcn/ui components, Next.js App Router admin layout from Phase 2

### Established Patterns
- Async throughout: `AsyncSession`, async service methods
- UUID PK with `default=uuid4` + `server_default=func.gen_random_uuid()`
- `tenant_id` ghost column on all models
- structlog for logging + Sentry for error tracking
- Offset-limit pagination (`?page=1&page_size=20`)
- Admin Bearer JWT auth (separate from player cookie auth)
- Money serialized as strings in API responses (`MoneyStr` / `Decimal -> str`)
- Audit events follow dotted taxonomy: `domain.action` (e.g., `wallet.recharge`)
- `from __future__ import annotations` NOT used in router files (Python 3.13 + FastAPI compatibility)
- Independent audit session for action-then-audit pattern

### Integration Points
- `backend/app/main.py` — Include new admin CRM router
- `backend/app/auth/models.py` — Ban enforcement logic (dependency or middleware check on `banned_at`)
- `backend/app/bets/router.py` — Add `banned_at` check before bet placement
- `frontend/app/admin/` — New pages: `users/`, `users/[id]/`, `audit-log/`
- `frontend/middleware.ts` — Admin Edge middleware already verifies Bearer (Phase 2)

</code_context>

<specifics>
## Specific Ideas

- El usuario dijo "todo en auto" — todas las decisiones tomadas por Claude basándose en convenciones del proyecto, requisitos del ROADMAP, y patrones de fases previas.
- La recharge UI en la detail page llama al primitivo existente de Phase 3 (`POST /admin/wallets/{user_id}/recharge`) — no se reimplementa la lógica de wallet.
- El audit log viewer es la señal de confianza para el operador (PITFALL #6): "mira, todo queda registrado y es inmutable".
- Las tablas admin deben sentirse como un SaaS real (TanStack + shadcn), no como un CRUD genérico.

</specifics>

<deferred>
## Deferred Ideas

- **Admin frontend para markets (CRUD visual)** — El backend API existe desde Phase 4, pero no hay UI admin para crear/editar/cerrar mercados. Podría añadirse como extensión de Phase 8 o como parte de Phase 10. No es un req de Phase 8.
- **Bulk actions en la user list** — Seleccionar múltiples usuarios y aplicar acciones masivas (ban, recharge, export). Sería útil con muchos usuarios, pero no es necesario para la demo.
- **Admin notification system** — Notificar al admin de eventos críticos (ej: reconciliation drift, settlement failures) dentro del CRM. Pertenece a Phase 11 hardening o v2.
- **User profile editing por el propio usuario** — El player no puede editar su display_name ni otros campos de perfil en v1. Diferido a una fase futura.

</deferred>

---

*Phase: 08-Admin CRM (User Management & Audit Log Viewer)*
*Context gathered: 2026-05-28*
