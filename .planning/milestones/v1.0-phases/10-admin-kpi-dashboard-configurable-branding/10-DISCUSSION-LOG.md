# Phase 10: Admin KPI Dashboard & Configurable Branding - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-31
**Phase:** 10-Admin KPI Dashboard & Configurable Branding
**Mode:** `--auto` (Pol chose "discuss auto → plan"). All gray areas auto-resolved with the recommended option; no interactive prompts. This log records the alternatives that were weighed.
**Areas discussed:** KPI freshness, House P&L derivation, DAU definition & window, Logo storage, Runtime theming, Admin landing/default-route, Chart fixture & empty state

---

## KPI freshness / computation strategy

| Option | Description | Selected |
|--------|-------------|----------|
| On-demand per request | Server Component awaits the KPI endpoint, `cache: "no-store"` (Phase 9 pattern). Simple; pulse-accurate. | ✓ |
| Periodic cache (Redis TTL) | Cache aggregates N minutes; faster but stale. | |
| Materialized / precomputed table | Precompute KPIs on a schedule; fastest, most infra. | |

**Choice:** On-demand per request (recommended default).
**Notes:** Single-tenant demo data volumes are modest; caching is premature. Revisit only if a query drags the landing render. → CONTEXT D-01.

---

## House P&L derivation

| Option | Description | Selected |
|--------|-------------|----------|
| Net flow on `house_revenue` ledger account | Compute today + cumulative from `entries`/`transfers` on the existing house account; no new account. | ✓ |
| Add a `house_expense` account | Match SC#2's literal formula by introducing a new ledger account. | |

**Choice:** Net flow on `house_revenue` (recommended default).
**Notes:** SC#2's literal `SUM(house_revenue) - SUM(house_expense)` references a `house_expense` account that **does not exist** (ledger has only `house_revenue` + `house_promo`). Derive from existing entries instead of inventing an account. ⚠️ Exact revenue-vs-expense entry/kind mapping to be validated in research against `backend/app/settlement/` + spike `settlement.md`. → CONTEXT D-03.

---

## DAU definition & window

| Option | Description | Selected |
|--------|-------------|----------|
| Activity proxies (bet OR login event), 24h default, UI toggle | Distinct users with a bet (`bets.created_at`) or audit login event in window; toggle 24h/7d/30d via query param. | ✓ |
| New `users.last_seen_at` column | Track last activity on a dedicated column; simpler query, schema churn. | |
| Fixed 24h, env-configured window | No UI control; window set by env var. | |

**Choice:** Activity proxies, 24h default, UI-configurable (recommended default).
**Notes:** `User` has no `last_login`/`last_seen` column today. Prefer reusing the audit log to avoid schema churn; a `last_seen_at` column is an acceptable alternative if query cost favors it. ⚠️ Validate source in research. → CONTEXT D-05.

---

## Logo storage

| Option | Description | Selected |
|--------|-------------|----------|
| base64/bytes in `tenant_config` row | Atomic config, no extra infra; served via endpoint. Size cap + type allowlist. | ✓ |
| Object storage (MinIO/S3) | Scalable, CDN-ready; but no object store in the docker-compose stack. | |
| Filesystem upload dir | Simple locally; awkward across containers/deploys. | |

**Choice:** base64/bytes in the `tenant_config` row (recommended default).
**Notes:** Single-tenant v1, no MinIO/S3 in the stack → keep deploy trivial and config atomic. Validation: content-type allowlist (PNG/SVG/JPEG/WebP) + ≤256 KB cap with clear errors (SC#4). Migrate to object storage/CDN in v2. → CONTEXT D-08.

---

## Runtime theming mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| CSS vars `--brand-*` injected on `:root` from `/branding/current` | Root layout (Server Component) fetches per navigation and renders a `<style>` setting the vars; Tailwind v4 `@theme inline` maps them to color tokens. Applies with no rebuild. | ✓ |
| Build-time theme (env/config baked at build) | Requires rebuild/redeploy to change — fails SC#5. | |
| Inline per-component style props | Scattered, hard to maintain. | |

**Choice:** Runtime CSS-var injection (recommended default).
**Notes:** Matches the existing `globals.css` Tailwind v4 `@theme inline` + `:root` setup. Per-navigation fetch (no static color inlining) makes a palette change apply on next navigation — the "live re-skin" demo money-shot (SC#5/SC#6). → CONTEXT D-10.

---

## Admin landing / default-route flag

| Option | Description | Selected |
|--------|-------------|----------|
| Dashboard IS `/admin` + sessionStorage default-route flag | Replace placeholder `admin/page.tsx`; login already redirects to `/admin`; small sessionStorage flag marks it the default route. | ✓ |
| Separate `/admin/dashboard` route + redirect | New route; extra redirect indirection. | |

**Choice:** Dashboard at `/admin` + sessionStorage flag (recommended default).
**Notes:** `adminLoginAction` already lands on `/admin`; minimal change, no router framework work. → CONTEXT D-11.

---

## Chart fixture & empty state

| Option | Description | Selected |
|--------|-------------|----------|
| 30-day synthetic seed + Recharts daily chart + empty state | Seed script generates 30 days of daily volume; chart renders ≤30 points; fresh-deploy empty state. | ✓ |
| No fixture (rely on real data) | Can't verify chart render on a fresh DB (fails SC#3). | |

**Choice:** Synthetic fixture + daily chart + empty state (recommended default).
**Notes:** Reuse Phase 9 Recharts/React-19 wiring; daily buckets → no downsampling. → CONTEXT D-06.

---

## Claude's Discretion

- Exact endpoint paths/grouping, migration filename/sequence, KPI SQL structure, card layout, chart type (area vs. line), error wording.
- DAU activity source (audit-log-derived vs. new `last_seen_at` column) — per D-05.
- `/branding/current` payload shape (single payload vs. split logo route) — per D-08.

## Deferred Ideas

- Object-storage / CDN logo hosting (v2).
- True multi-tenant per-tenant theming (v2).
- Real-time KPI push / auto-refreshing dashboard.
- Materialized / precomputed KPI tables (only if on-demand is slow).
- Additional KPI cards beyond the five required.
- Admin market-management CRUD UI (backend exists; UI deferred, not an ADD-* req).
