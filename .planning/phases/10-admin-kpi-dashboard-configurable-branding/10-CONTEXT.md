# Phase 10: Admin KPI Dashboard & Configurable Branding - Context

**Gathered:** 2026-05-31
**Status:** Ready for planning
**Mode:** Smart discuss (`--auto`) — all gray areas auto-resolved with the recommended option (Pol chose "discuss auto → plan"). Decisions below are defaults grounded in the ROADMAP success criteria, prior-phase patterns, and the real codebase; planning may refine the ones flagged "validate in research".

<domain>
## Phase Boundary

Two deliverables on the **admin** surface:

1. **KPI dashboard** — replace the placeholder admin landing (`frontend/src/app/admin/page.tsx`) with the operator's "is this platform healthy?" 5-second pulse: five KPI cards (24h bet volume, daily active users, total active markets, pending resolutions, house P&L today + cumulative) plus a Recharts volume-over-time chart (daily granularity, first 30 days). Logging in lands the admin here by default.
2. **Configurable branding** — a single-row `tenant_config` table + admin CRUD form (brand name, logo image, primary/secondary palette) consumed at runtime by the player-facing UI (CSS variables), so a palette change applies on next navigation with no rebuild/redeploy. This is the white-label sales wedge.

Delivers **ADD-01, ADD-02, ADD-03, ADD-05, ADD-06** (ADD-04 audit viewer already shipped in Phase 8).

**In scope:**
- Backend KPI aggregation endpoint(s) (admin-gated), `tenant_config` model + migration + admin CRUD endpoints, public `GET /branding/current` (+ logo serving), a 30-day synthetic volume fixture/seed for chart verification.
- Frontend KPI dashboard at `/admin` (cards + Recharts chart + empty state), admin branding form, runtime branding consumption in the player root layout, admin-nav link to the dashboard.
- Negative test: player request to `/admin/tenant-config` → 403 (reuse Phase 8 `current_active_admin`).

**Out of scope (other phases / deferred):**
- Mobile-responsiveness *validation* pass + hardening → Phase 11.
- Object-storage / CDN logo hosting, true multi-tenant per-tenant theming → v2 (single-tenant in v1).
- Real-time push of KPI updates, materialized/precomputed KPI tables, additional KPI cards beyond the five required.
- Admin market-management CRUD UI (backend exists from Phase 4; UI was noted as deferred in Phase 8) — not an ADD-* req for this phase.

</domain>

<decisions>
## Implementation Decisions

### KPI Dashboard — data & computation
- **D-01: On-demand computation per request.** The dashboard is a Server Component that `await`s an admin KPI endpoint (`cache: "no-store"`, mirroring the Phase 9 server-component fetch pattern). No Redis cache / materialized table in v1 — single-tenant demo data volumes are modest and "pulse" accuracy beats micro-optimization. If a specific aggregate is slow (notably the 30-day chart), aggregate server-side with daily buckets (≤30 points → no downsampling needed). *Revisit caching only if a query measurably drags the landing render.*
- **D-02: The five cards are fixed by SC#2.** 24h bet volume (`SUM(stake)` over `bets.created_at >= now-24h`), DAU (see D-05), total active markets (`COUNT(markets WHERE status = OPEN)`), pending resolutions (see D-04), house P&L today + cumulative (see D-03). Money rendered as **strings** (project money-as-string convention), never JSON floats.
- **D-03: House P&L derived from ledger net flow on the house account(s).** SC#2's literal formula is `SUM(house_revenue) - SUM(house_expense)`, **but the ledger has no `house_expense` account** — only `house_revenue` (sink, opening 0) and `house_promo` (funded source) exist (`backend/app/wallet/constants.py`). **Decision:** compute P&L from net flow through the `house_revenue` account in the `entries`/`transfers` ledger (credits = house take on losing stakes / rake; debits = house-funded payouts), split into "today" and "cumulative". ⚠️ **Validate in research:** the exact entry/kind mapping that constitutes house revenue vs. house expense for settled bets — read the settlement ledger semantics (`backend/app/settlement/`, spike-findings `settlement.md`) before locking the SQL. Do **not** invent a new account; derive from existing entries.

### KPI Dashboard — Daily Active Users
- **D-04: Pending resolutions = markets past their resolution point awaiting admin action.** Mirrored (`source = POLYMARKET`) markets past their end/`deadline` + house (`source = HOUSE`) markets past `deadline`, that are not yet `RESOLVED`/`CANCELLED` (i.e. `status = CLOSED` or OPEN-past-deadline with `resolved_at IS NULL`). Map to `markets.status` (enum DRAFT/OPEN/CLOSED/RESOLVED/CANCELLED) + `markets.deadline` + `markets.source` during planning.
- **D-05: DAU from activity proxies, default 24h window, UI-configurable.** The `User` model has **no `last_login`/`last_seen` column**. "Active" = distinct user IDs with activity in the window, where activity = placed a bet (`bets.created_at`) **OR** a successful login event in the audit log (`auth.login_*` from `core/audit`). Window default **24h**, configurable via a card-level toggle (24h / 7d / 30d) passed as a **query param** to the KPI endpoint — keep it interactive on the card, not an env var or `tenant_config` field. ⚠️ **Validate in research:** prefer reusing the audit log to avoid schema churn; if that's awkward, a lightweight `users.last_seen_at` column updated on login is an acceptable alternative — planner picks based on query cost. State the choice and the source explicitly.

### KPI Dashboard — chart & empty state
- **D-06: Recharts daily-granularity volume chart + 30-day synthetic fixture.** Recharts `^3.8.1` is already installed (Phase 9); reuse its React-19/`react-is` setup and the Phase 9 chart/empty-state conventions. Daily buckets for the first 30 days of activity. Ship a backend seed/fixture generating 30 days of synthetic daily bet-volume so the chart's render (and absence of slowdowns) is verifiable on a fresh DB. **Empty state:** a fresh deployment (no activity) shows a friendly "No activity yet — data appears as bets are placed" placeholder, not a broken/empty axis.

### Branding — storage & validation
- **D-07: Single-row `tenant_config` table.** New model + Alembic migration (next sequence number off the current single head). Columns: brand name, logo (see D-08), primary/secondary palette hex, plus the standard `tenant_id` ghost column + timestamps. Enforced single row (fixed PK / unique constraint) — this is the single-tenant seam toward multi-tenant v2.
- **D-08: Logo stored as bytes/base64 in the `tenant_config` row, served via a dedicated endpoint.** No object storage (no MinIO/S3 in the docker-compose stack) and no filesystem upload dir → keep deploy trivial and config atomic. The player UI references the logo via `GET /branding/logo` (or a data URI for small assets). **Validation (SC#4):** content-type allowlist (PNG / SVG / JPEG / WebP) + a size cap (e.g. ≤256 KB) → clear, specific error messages on reject. *Migrate to object storage/CDN in v2 — deferred.*
- **D-09: Server-side hex validation.** The branding form rejects invalid hex colors (and oversized logos) with clear field-level errors before persisting (SC#4). Validate on the backend (source of truth); the frontend may also pre-validate for UX.

### Branding — runtime theming consumption
- **D-10: CSS custom properties injected at runtime — no rebuild.** The frontend is **Tailwind v4** using `@theme inline` + CSS vars on `:root` (`frontend/src/app/globals.css` currently defines only `--background`/`--foreground`). **Decision:** add `--brand-primary` / `--brand-secondary` mapped through `@theme inline` to color tokens (e.g. `--color-brand-primary` → usable as `bg-brand-primary`/`text-brand-primary`). The player **root layout** (Server Component) `await`s `GET /branding/current` and renders a `<style>` block setting `:root { --brand-primary: <hex>; --brand-secondary: <hex>; }`. Because the layout fetches per navigation (no static inlining of colors), changing the palette in admin applies on **next page navigation** with zero rebuild/redeploy (SC#5, SC#6). Brand name + logo are consumed from the same `/branding/current` payload.

### Admin landing & auth
- **D-11: The KPI dashboard IS `/admin`.** Replace the placeholder body of `frontend/src/app/admin/page.tsx`; `adminLoginAction` already redirects to `/admin`, so the dashboard becomes the landing automatically. SC#1's "session-storage default-route flag" = a small client-side flag in `sessionStorage` marking `/admin` (dashboard) as the default admin route so post-login navigation consistently lands there across sessions. Keep it minimal — no router framework changes.
- **D-12: Reuse Phase 8 admin auth.** All new admin endpoints (KPI, tenant-config CRUD) are gated by `current_active_admin` (Bearer JWT, separate from player cookie auth). `GET /branding/current` + `GET /branding/logo` are **public** (the player UI is unauthenticated for branding). SC#6 negative test: a player request to `/admin/tenant-config` returns **403**.

### Claude's Discretion
- Exact endpoint paths/grouping (`/admin/dashboard/kpis` vs. per-card endpoints; `/admin/tenant-config` GET/PUT shape), migration filename/sequence, KPI SQL structure, card component layout/spacing, chart type (area vs. line), error-message wording, and whether the DAU activity source is audit-log-derived or a new `last_seen_at` column (per D-05).
- Whether `/branding/current` returns colors+name+logo-url in one payload or splits logo to its own route (per D-08).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & Roadmap
- `.planning/ROADMAP.md` §Phase 10 — goal + the **6 success criteria** (the binding contract for this phase) + "demo-trap branding" pitfall.
- `.planning/REQUIREMENTS.md` §Admin — Dashboard & Branding — ADD-01, ADD-02, ADD-03, ADD-05, ADD-06.

### Prior Phase Context (foundations this phase builds on)
- `.planning/phases/08-admin-crm-user-management-audit-log-viewer/08-CONTEXT.md` — admin Bearer auth (`current_active_admin`), admin layout/nav, TanStack+shadcn admin UI feel, audit-event taxonomy, money-as-string, `tenant_id` ghost column.
- `.planning/phases/09-user-app-ux-polish-market-detail-real-time/09-CONTEXT.md` — Recharts setup (react-is ↔ React 19), Server-Component fetch pattern (`cache: "no-store"`), empty/loading/error-state conventions, money/odds as strings.
- `.planning/phases/03-wallet-double-entry-ledger/03-CONTEXT.md` — double-entry ledger model + house accounts; basis for the house-P&L derivation (D-03).

### Spike findings (proven patterns / constraints)
- `Skill("spike-findings-xpredict")` — money `Decimal`/`NUMERIC(18,4)` never float; settlement ledger semantics (`references/settlement.md`) needed to map house revenue vs. expense for D-03.

### Existing code (critical to read)
- `frontend/src/app/admin/page.tsx` — placeholder landing this phase **replaces** with the dashboard (D-11).
- `frontend/src/app/admin/layout.tsx` + `frontend/src/components/admin/admin-nav.tsx` — admin shell/nav to extend with a dashboard link.
- `frontend/src/app/globals.css` — Tailwind v4 `@theme inline` + `:root` CSS vars: the runtime-theming hook (D-10).
- `backend/app/wallet/constants.py`, `backend/app/wallet/models.py`, `backend/app/wallet/service.py` — house accounts (`house_revenue`/`house_promo`) + ledger writer for P&L (D-03).
- `backend/app/settlement/` — settlement ledger entries (validate house revenue/expense mapping for D-03).
- `backend/app/markets/models.py` + `backend/app/markets/enums.py` — `Market.status` (enum) + `deadline` + `source` for active-markets (D-02) and pending-resolutions (D-04) counts.
- `backend/app/bets/` (models + router) — `bets.stake`/`created_at` for 24h volume + DAU proxy.
- `backend/app/core/audit/` (service + models) — login events for the DAU activity proxy (D-05).
- `backend/app/auth/deps.py` (`current_active_admin`) + `backend/app/auth/admin_router.py` — admin endpoint gating (D-12) + SC#6 negative test.
- `backend/app/main.py` — wire the new admin KPI + tenant-config routers + public branding router.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Admin auth**: `current_active_admin` Bearer dependency (Phase 2/8) — gate every new `/admin/*` endpoint with it.
- **Admin UI shell**: `admin/layout.tsx` + `admin-nav.tsx` (Phase 8) — add the dashboard nav entry; reuse shadcn card/table/badge components.
- **Recharts**: `recharts ^3.8.1` already in `frontend/package.json` (Phase 9) — reuse the React-19 wiring and chart/empty-state patterns.
- **Server-component fetch**: Phase 9 `lib/api.ts` pattern (async Server Component, `NEXT_PUBLIC_API_URL`, `cache: "no-store"`) — extend for KPI + branding fetches.
- **Ledger**: `WalletService` + house accounts for P&L; never bypass the ledger writer.
- **Money discipline**: `NUMERIC(18,4)` + `Decimal`; serialize as strings (money-lint gate enforces this in CI).

### Established Patterns
- Async throughout (`AsyncSession`); UUID PKs; `tenant_id` ghost column on every table; structlog + Sentry; offset-limit pagination; audit events `domain.action`; admin Bearer auth separate from player cookie auth; `from __future__ import annotations` NOT used in router files.

### Integration Points
- New backend routers: admin KPI, admin tenant-config CRUD, public branding (`/branding/current` + `/branding/logo`) — included in `backend/app/main.py`.
- New migration: `tenant_config` table (off the current single Alembic head; preserve the single-head invariant).
- Frontend: replace `admin/page.tsx` body with the dashboard; new branding form page under `/admin`; **player root layout** edited to inject branding CSS vars at runtime; `globals.css` extended with `--brand-*` tokens.

</code_context>

<specifics>
## Specific Ideas

- Branding is the **white-label sales wedge** — the palette/logo swap must visibly change the player UI *without a rebuild* (SC#5). That "live re-skin" is the demo money-shot; the per-navigation CSS-var injection (D-10) is what makes it real rather than a demo trap.
- The dashboard is a **5-second health pulse**, not an analytics suite — five cards + one chart, legible at a glance.
- Pol chose `--auto` discuss → **plan** (stop after PLAN.md for his review before execution). The two ⚠️ research-flagged items (D-03 house P&L mapping, D-05 DAU activity source) are the only soft spots — planning/research should pin them against the real ledger + audit schemas.

</specifics>

<deferred>
## Deferred Ideas

- **Object-storage / CDN logo hosting** — base64-in-row is the v1 choice (D-08); migrate when multi-tenant v2 + CDN land.
- **True multi-tenant per-tenant theming** — v1 is single-row `tenant_config`; per-tenant resolution is v2.
- **Real-time KPI push / auto-refreshing dashboard** — v1 computes on page load (D-01); live push is a later nicety.
- **Materialized / precomputed KPI tables** — only if on-demand aggregation becomes slow.
- **Additional KPI cards** beyond the five required (e.g. conversion funnel, retention) — out of scope for the pulse.
- **Admin market-management CRUD UI** — backend exists (Phase 4); UI deferred (noted in Phase 8), not an ADD-* req here.

</deferred>

---

*Phase: 10-Admin KPI Dashboard & Configurable Branding*
*Context gathered: 2026-05-31*
