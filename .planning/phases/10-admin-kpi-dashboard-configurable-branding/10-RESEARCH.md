# Phase 10: Admin KPI Dashboard & Configurable Branding - Research

**Researched:** 2026-05-31
**Domain:** Brownfield admin analytics (ledger-derived KPIs) + runtime white-label theming on an existing FastAPI/SQLAlchemy-async/Postgres + Next.js/Tailwind-v4 stack
**Confidence:** HIGH (every recommendation below is grounded in the actual merged codebase, read this session; the two flagged unknowns are resolved against real ledger + audit schemas)

## Summary

This is a brownfield phase. The single highest-value output is resolving the two ⚠️ flagged unknowns against the *real* code, which I did by reading the wallet/settlement/audit/markets/bets source directly. Both flagged formulas in the ROADMAP success criteria are subtly wrong against the implemented schema, and the planner must NOT copy them verbatim:

1. **House P&L (D-03 / SC#2):** SC#2 says `SUM(house_revenue) - SUM(house_expense)`. **There is no `house_expense` account and there never was** — the ledger has exactly three account kinds (`user_wallet`, `house_promo`, `house_revenue`). The house *earns* losing stakes (swept into `house_revenue`) and *pays* winners' net winnings (funded out of `house_promo`). P&L is therefore the **net of house-revenue credits minus house-promo winnings debits**, not a difference of two `house_*` balances. The exact derivation, kinds, and sign convention are in the §House P&L Derivation section.

2. **DAU (D-05 / SC#2):** The `User` model has **no `last_login`/`last_seen` column** (confirmed). Worse than CONTEXT assumed: **the bets module emits NO audit event** — there is no `bet.placed`/`bet_placed` row in `audit_log` (the `bet_placed` literal in `app/bets/constants.py` is a *transfer kind*, not an audit event; `KNOWN_EVENT_TYPES` lists `bet.placed` but no code writes it). The only user-activity signal in the audit log is the **login event `auth.session_started`** (note: NOT `auth.login_*` as CONTEXT/`KNOWN_EVENT_TYPES` suggest), with `actor = "user:<uuid>"`. So an audit-log-only DAU undercounts active bettors who didn't re-login in the window. Recommendation (with query + cost) is a **UNION of distinct bettor ids from `bets.created_at` and distinct user ids parsed from `audit_log.actor` for `auth.session_started`** — no schema churn, no `last_seen_at` column needed.

**Primary recommendation:** Build one admin KPI service that computes all five cards from the existing ledger/markets/bets/audit tables with the exact predicates documented below; add a single-row `tenant_config` table (migration off head `0008_phase8_user_created_at`) with base64 logo bytes; inject `--brand-primary`/`--brand-secondary` via a `<style>` block in the player root layout that `await`s a public `GET /branding/current`. Mirror Phase 8's admin-router + money-as-string + 403-negative-test patterns and Phase 9's `PriceHistoryChart` + Server-Component fetch patterns verbatim.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| KPI aggregation (5 cards + 30d chart) | API / Backend (`app/admin` KPI service) | Database (raw ledger/markets/bets/audit SUM/COUNT) | All five KPIs are read-only aggregates over existing tables; compute server-side, serialize money as strings. Never compute money in JS. |
| House P&L derivation | Database (ledger `entries`/`transfers`) | API | Truth is the append-only ledger; P&L is a SUM over `entries` filtered by transfer `kind` + account. |
| DAU rolling-window count | Database (distinct over `bets` + `audit_log`) | API (window query param) | Two activity proxies UNIONed; cheap with existing indexes. |
| Branding persistence + validation | API / Backend (`tenant_config` model + admin CRUD) | Database (single-row table) | Hex + logo size/content-type validation is server-side (source of truth, SC#4). |
| Logo serving | API / Backend (public `GET /branding/logo`) | — | Bytes-in-row, served with correct `Content-Type`; no object storage in stack. |
| Runtime theming (CSS vars) | Frontend Server (root layout `await`s `/branding/current`, renders `<style>`) | Browser (CSS var cascade) | Per-navigation fetch = no rebuild; the white-label money-shot. |
| Admin auth gate | API / Backend (`current_active_admin`) | Frontend (optimistic middleware) | Authoritative gate is FastAPI Bearer; the edge middleware is optimistic only. |

## Standard Stack

Everything needed is **already installed**. This phase adds **zero new runtime dependencies** on either side.

### Core (backend — already present)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI + SQLAlchemy 2 async | (in repo) | Routers + async ORM aggregates | Project standard; `AsyncSession` everywhere `[VERIFIED: codebase]` |
| Alembic | (in repo) | `tenant_config` migration off head `0008` | Single-head invariant `[VERIFIED: codebase]` |
| Pydantic v2 | (in repo) | Response schemas; `MoneyStr` money-as-string + `extra="forbid"` | Reuse `app/wallet/schemas.MoneyStr`, `app/markets/schemas.PaginatedResponse` `[VERIFIED: codebase]` |

### Core (frontend — already present)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Next.js | `^16.2.6` | App Router, Server Components | NOTE: it's Next **16**, not 15 (CONTEXT said 15) — confirm in plans `[VERIFIED: frontend/package.json]` |
| React / react-dom | `^19.0.0` | UI | `[VERIFIED: package.json]` |
| recharts | `^3.8.1` | Volume-over-time chart | Already wired for React 19 `[VERIFIED: package.json]` |
| react-is | `19.2.6` (pinned via `pnpm.overrides: { "react-is": "$react-is" }`) | Recharts ↔ React 19 compat | The exact fix Phase 9 baked in; do NOT touch `[VERIFIED: package.json]` |
| tailwindcss | `^4.0.0` + `@tailwindcss/postcss` | `@theme inline` CSS-var theming | Runtime-var hook in `globals.css` `[VERIFIED: package.json + globals.css]` |
| shadcn/ui primitives (`@radix-ui/*`, `class-variance-authority`, `lucide-react`, `sonner`) | (in repo) | KPI cards, branding form, toasts | Reuse existing `components/ui/*` `[VERIFIED: package.json]` |
| react-hook-form + zod + @hookform/resolvers | (in repo) | Branding form + client pre-validation | Already present for forms `[VERIFIED: package.json]` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| On-demand KPI compute (D-01) | Redis cache / materialized table | Deferred (CONTEXT) — single-tenant demo volumes are modest; revisit only if the 30-day chart query measurably drags landing render. |
| base64 logo in-row (D-08) | MinIO/S3 object storage | No object storage in the docker-compose stack; deferred to v2. |
| `<style>` block CSS-var injection (D-10) | Inline style on `<html>` / cookie-themed CSS | `<style>` in a Server Component re-fetched per navigation is the simplest no-rebuild path and matches the existing `:root`/`@theme inline` structure. |

**Installation:** none required (backend + frontend deps already satisfied). The only new artifact is the Alembic migration for `tenant_config`.

## Package Legitimacy Audit

> Not applicable — this phase installs **no new packages** on backend or frontend. Every library used (FastAPI, SQLAlchemy, Alembic, Pydantic, Next.js, React, Recharts, react-is, Tailwind, shadcn/Radix, react-hook-form, zod) is already a committed, in-use dependency verified present in `frontend/package.json` and the backend environment this session. No registry resolution or slopcheck gate is needed because no `npm install` / `pip install` of a new name occurs. If planning later decides to add a hex-validation or image-sniffing helper, run the Package Legitimacy Gate before adding it — but the recommendation below is to use stdlib/existing deps instead (see §Don't Hand-Roll).

---

## ⚠️ FLAGGED UNKNOWN 1 — House P&L Derivation (D-03 / SC#2)

**Verdict: SC#2's literal formula `SUM(house_revenue) - SUM(house_expense)` is NOT implementable as written. Do not copy it into the plan.** `[VERIFIED: codebase]`

### What the ledger actually contains

Account kinds (`app/wallet/constants.py`) — there are exactly three; **no `house_expense`**:
- `user_wallet`
- `house_promo` — seeded UUID `00000000-0000-0000-0000-0000000000a1` (`HOUSE_PROMO_ACCOUNT_ID`), funded **source** (large opening balance).
- `house_revenue` — seeded UUID `00000000-0000-0000-0000-0000000000a2` (`HOUSE_REVENUE_ACCOUNT_ID`), **sink**, opens at 0.

Plus a per-market `market_liability` account (kind `market_liability`, `owner_type='market'`) from Phase 5.

### How money actually moves through the house at settlement

From `app/settlement/service.py` + `app/settlement/constants.py` (read this session):

| Settlement leg | Transfer `kind` | Debit account | Credit account | Amount | House effect |
|----------------|-----------------|---------------|----------------|--------|--------------|
| Winner stake return | `settle_stake_return` | `market_liability` | winner `user_wallet` | `stake` | **neutral** (no house account touched) |
| Winner winnings | `settle_winnings` | `house_promo` (`…a1`) | winner `user_wallet` | `payout - stake` (>0; skipped when price==1.0) | **HOUSE EXPENSE** (house funds the fixed-odds shortfall) |
| Loser sweep | `settle_loss` | `market_liability` | `house_revenue` (`…a2`) | `stake` | **HOUSE REVENUE** (lost stake becomes revenue) |

Bet placement (Phase 5) debits `user_wallet` → credits `market_liability` (kind `bet_placed`) — **never touches a house account**, so it is correctly excluded from P&L. Reversals (kind `reverse_*`) post the exact inverses and MUST be netted in (see below) so a reversed settlement doesn't leave phantom P&L.

The spike `references/settlement.md` confirms the model: *"Losers' stakes stay in market_liability … they fund winner payouts"* and *"in a balanced 50/50 binary market, house_revenue = 0 — the house only profits from market imbalance."* But note the spike's simplified prose ("remaining pot → house_revenue") is **not** what the production code does — production sweeps each **loser's** stake individually (`settle_loss`) and funds each **winner's** winnings from `house_promo` (`settle_winnings`). Trust the production code, not the spike prose.

### The exact derivation (LOCK THIS)

> **House P&L = (house revenue earned) − (house winnings paid)**
> = `SUM(entries.amount WHERE direction='credit' AND account=house_revenue)`
> − `SUM(entries.amount WHERE direction='debit' AND account=house_promo AND transfer.kind IN ('settle_winnings','reverse_winnings'…))`

Two equally valid, equivalent SQL strategies. **Strategy B (kind-filtered net flow) is recommended** because it is robust to `house_promo` also being used for recharges/signup bonuses, which are NOT house P&L.

> **Why not "just sum the two house balances"?** `house_promo` is also the source for `recharge` and `signup_bonus` transfers (player funding), and `house_revenue` only ever receives `settle_loss`. So `house_promo.balance` mixes player-funding outflow with settlement winnings; you cannot read P&L off raw balances. You MUST filter by transfer `kind`.

**Strategy B — kind-filtered, time-bounded (recommended). Revenue and expense in one pass:**

```sql
-- House P&L over a time window [lo, hi). Run twice: today (lo = date_trunc('day', now()))
-- and cumulative (lo = '-infinity' / omit the lower bound).
SELECT
  COALESCE(SUM(CASE
    WHEN t.kind = 'settle_loss'    THEN e.amount   -- revenue in
    WHEN t.kind = 'reverse_loss'   THEN -e.amount  -- revenue undone
    ELSE 0 END), 0)
  -
  COALESCE(SUM(CASE
    WHEN t.kind = 'settle_winnings'  THEN e.amount  -- expense out
    WHEN t.kind = 'reverse_winnings' THEN -e.amount -- expense undone
    ELSE 0 END), 0)
  AS house_pnl
FROM entries e
JOIN transfers t ON t.id = e.transfer_id
WHERE e.created_at >= :lo            -- omit for cumulative
  AND e.created_at <  :hi            -- :hi = now() for "today"; omit for cumulative
  AND t.kind IN ('settle_loss','reverse_loss','settle_winnings','reverse_winnings');
```

Notes for the planner:
- **Direction is implied by kind here** (every `settle_loss` entry pair has the `house_revenue` credit leg as its revenue; every `settle_winnings` pair has the `house_promo` debit leg as its expense). To be maximally explicit and index-friendly, the planner MAY additionally constrain `e.account_id = HOUSE_REVENUE_ACCOUNT_ID AND e.direction='credit'` for the revenue arm and `e.account_id = HOUSE_PROMO_ACCOUNT_ID AND e.direction='debit'` for the expense arm. Either is correct; the account-constrained form hits the `entries_account_idx` index.
- **Money type:** `entries.amount` is `Money` = `NUMERIC(18,4)`. The result is a `Decimal`; serialize with `MoneyStr` (string), never a JSON float. A negative P&L (more winnings than revenue) is valid and must render as a negative string.
- **"Today" boundary:** use `date_trunc('day', now())` for `lo` and `now()` for `hi`. **Timezone discipline** — `created_at` columns are `DateTime(timezone=True)`; pick a consistent app timezone for "today" (project convention is UTC unless STATE/CONVENTIONS says otherwise — planner should confirm, it's the one genuine ambiguity).
- **ORM form:** build with `select(func.coalesce(func.sum(case(...)),0))`, joining `Entry`→`Transfer`. Reuse the `entries`+`transfers` join already proven in `WalletService.get_transactions`.

**Ambiguity the planner MUST lock (one item):** whether "today" is UTC midnight or a configured display timezone. Everything else above is determined by the code.

---

## ⚠️ FLAGGED UNKNOWN 2 — DAU Activity Source (D-05 / SC#2)

**Verdict: Use a UNION of distinct bettor ids (`bets`) + distinct login user ids (`audit_log`). Do NOT add a `last_seen_at` column — it would not capture bets-without-login and adds schema churn for no gain.** `[VERIFIED: codebase]`

### What's actually available (and what isn't)

- `users` has **no** `last_login`/`last_seen` column (`app/auth/models.py`, read this session). Confirmed.
- **Bets do NOT write an audit event.** `app/bets/` imports no `AuditService`; the only `bet_placed`/`bet.placed` references are: (a) `TRANSFER_BET_PLACED = "bet_placed"` in `app/bets/constants.py` (a *transfer kind*), and (b) `"bet.placed"` in `KNOWN_EVENT_TYPES` (a dropdown list that overstates reality — no code emits it). So **the audit log captures logins but not bets.** `[VERIFIED: grep app/bets + codebase]`
- The **login activity event is `auth.session_started`**, written in `app/auth/router.py:176` on successful player login, with `actor = f"user:{user.id}"` and `payload = {"email": ...}`. (CONTEXT/`KNOWN_EVENT_TYPES` reference `auth.login_started`/`auth.login_*`, which **does not exist as an emitted event** — `KNOWN_EVENT_TYPES` is stale. Use `auth.session_started`.) Admin login is `auth.admin_login_started`. `[VERIFIED: app/auth/router.py + grep]`
- `bets` has `user_id` (indexed, `bets_user_idx`) + `created_at` (`DateTime(timezone=True)`). Distinct-bettor counts over a window are cheap. `[VERIFIED: app/bets/models.py]`
- `audit_log` has `actor` (Text, format `user:<uuid>`) + `occurred_at` (indexed via the viewer's `order_by`; there is an implicit need — confirm an index on `occurred_at` exists or the count will seq-scan; the viewer already filters on it). `[VERIFIED: app/core/audit/models.py + router.py]`

### Why audit-log-only (the CONTEXT-preferred path) is insufficient alone

Because bets emit no audit event, an audit-only DAU = **logins only**. A player with a persistent session who places bets across days without re-logging-in would be invisible. For a betting platform the bettor is the most important "active user," so logins-only materially undercounts. The cheapest correct proxy is **(placed a bet) OR (logged in)** in the window — exactly D-05's stated definition.

### Recommended query (LOCK THIS)

Default window 24h, configurable via a card-level toggle passed as a query param (`window=24h|7d|30d` → translate to an interval). Count distinct users across both sources:

```sql
-- :lo = now() - :interval  (24h / 7d / 30d)
SELECT COUNT(*) FROM (
  SELECT user_id            AS uid FROM bets      WHERE created_at >= :lo
  UNION                                   -- UNION (not UNION ALL) dedups across sources
  SELECT (split_part(actor, ':', 2))::uuid AS uid
    FROM audit_log
    WHERE event_type = 'auth.session_started'
      AND occurred_at >= :lo
      AND actor LIKE 'user:%'
) AS active_users;
```

- `bets.user_id` is already a UUID; `audit_log.actor` is `user:<uuid>` text → parse with `split_part(actor, ':', 2)::uuid`. Only `actor LIKE 'user:%'` rows are users (skip `system`/`admin`).
- `UNION` (set, not `UNION ALL`) handles a user who both bet and logged in.
- **Cost:** two indexed range scans (`bets_user_idx` is on `user_id`, not `created_at` — at demo volumes a small range filter is fine; if `bets` grows, add an index on `bets(created_at)` and `audit_log(occurred_at)` — flag as a cheap optional follow-up, not a blocker). Distinct over a 24h–30d window at single-tenant demo scale is trivially fast.
- **ORM form:** two `select(...)` statements combined with `.union()`, wrapped in `select(func.count()).select_from(subq)` — same shape as the audit viewer's count.

**Do NOT add `users.last_seen_at`.** It only captures logins (same blind spot as audit-only), requires a migration + a write on every login (hot-path write amplification), and still misses the bet signal. The UNION proxy is strictly better and schema-free.

**Ambiguity the planner should note:** whether to include admin logins (`auth.admin_login_started`) in DAU. Recommendation: **exclude admins** (DAU = players); filter `event_type = 'auth.session_started'` only.

---

## Other Code-Grounded KPI Findings

### Total active markets (D-02)
`COUNT(markets WHERE status = 'OPEN')`. `MarketStatus` enum = DRAFT/OPEN/CLOSED/RESOLVED/CANCELLED (`app/markets/enums.py`). "Active" = currently open for betting = `status='OPEN'`. `status` is a `String(20)` column with a CHECK constraint; compare against the literal `'OPEN'`. `[VERIFIED: app/markets/models.py + enums.py]`

### Pending resolutions (D-04)
Markets past their resolution point, not yet finalized, awaiting admin action. **Single column for both sources:** `markets.deadline` (NOT NULL, `DateTime(timezone=True)`). **The Phase 6 Polymarket sync migration added NO separate end-date column** — it added only `volume`, `volume_24hr`, `polymarket_slug` (`0004_phase6_polymarket_sync.py`, read this session). So `deadline` is the resolution point for both HOUSE and POLYMARKET markets; there is no `endDate` column to special-case (the ROADMAP's "mirrored markets past `endDate`" maps to `markets.deadline` in our DB). `resolved_at` / `closed_at` exist as nullable timestamps. `[VERIFIED: migration 0004 + app/markets/models.py]`

Recommended predicate:
```sql
SELECT COUNT(*) FROM markets
WHERE deadline < now()
  AND status NOT IN ('RESOLVED','CANCELLED','DRAFT');
-- i.e. status IN ('OPEN','CLOSED') with a past deadline, not yet finalized.
```
`resolved_at IS NULL` is equivalent to `status NOT IN ('RESOLVED','CANCELLED')` here (settlement sets both atomically). The planner should pick the status form (it's the indexed/cheap path) and confirm DRAFT exclusion (a never-opened market past a placeholder deadline is not "pending resolution").

### 24h bet volume (D-02)
`SUM(bets.stake) WHERE created_at >= now() - interval '24 hours'`. `bets.stake` is `Money` (`NUMERIC(18,4)`); `created_at` is `DateTime(timezone=True)`. Serialize as `MoneyStr`. `COALESCE(..., 0)` for the no-bets case. `[VERIFIED: app/bets/models.py]`
> Do NOT use `markets.volume`/`volume_24hr` for this card — those are Polymarket-synced replication fields (external data), not internal bet stake totals.

### 30-day daily volume chart (D-06)
Aggregate server-side into ≤30 daily buckets (no client downsampling):
```sql
SELECT date_trunc('day', created_at) AS day, COALESCE(SUM(stake),0) AS volume
FROM bets
WHERE created_at >= now() - interval '30 days'
GROUP BY day ORDER BY day;
```
Return `[{ "day": ISO, "volume": "string" }]`. The synthetic 30-day fixture (CONTEXT D-06) seeds `bets` rows across 30 days so the chart renders without slowdown on a fresh DB. Empty state: fewer than ~1 bucket → friendly placeholder (mirror `PriceHistoryChart`'s `<2 points` empty state).

---

## Architecture Patterns

### System Architecture Diagram

```
                          ┌─────────────────────────── ADMIN (Bearer JWT) ───────────────────────────┐
ADMIN BROWSER             │                                                                            │
  /admin  (Server Comp.) ─┼─ await GET /api/v1/admin/dashboard/kpis?window=24h  ──► [current_active_admin]
   KPI cards + Recharts    │                                          │                                 │
                           │                                          ▼                                 │
                           │                              KpiService (read-only aggregates)             │
                           │            ┌─────────────┬───────────────┼──────────────┬──────────────┐  │
                           │            ▼             ▼               ▼              ▼              ▼  │
                           │   SUM(bets.stake)  COUNT(markets    COUNT(markets   DAU UNION    house P&L│
                           │     24h window      status=OPEN)    deadline<now,   (bets ∪      (entries  │
                           │                                     not finalized)  auth logins)  by kind) │
  /admin/branding (form) ──┼─ PUT /api/v1/admin/tenant-config ──► [current_active_admin]                │
                           │      (brand_name, logo bytes, primary/secondary hex; server validates)     │
                           └────────────────────────────────────────────────────────────────────────────┘

                          ┌────────────────────────── PLAYER (public) ───────────────────────────────┐
PLAYER BROWSER            │                                                                            │
  any page (root layout) ─┼─ await GET /branding/current  ──►  tenant_config (single row)              │
   <style>:root{--brand-* │        (brand_name, primary_hex, secondary_hex, logo_url)                  │
     :<hex from API>}</…>  │                                                                            │
   <img src=/branding/logo>┼─ GET /branding/logo  ──► tenant_config.logo bytes + content_type           │
                           └────────────────────────────────────────────────────────────────────────────┘

Data sources (existing tables, READ-ONLY for KPIs):
  entries+transfers (ledger) ─ house P&L      bets ─ volume + DAU      markets ─ active + pending
  audit_log (auth.session_started) ─ DAU login proxy
```

### Recommended endpoint grouping (Claude's discretion per CONTEXT)
- `GET /api/v1/admin/dashboard/kpis?window=24h|7d|30d` → one payload with all five cards + the 30-day chart buckets (single round-trip; the dashboard is one Server-Component render). Admin-gated.
- `GET /api/v1/admin/tenant-config` + `PUT /api/v1/admin/tenant-config` → branding CRUD. Admin-gated.
- `GET /branding/current` (public) → `{ brand_name, primary_hex, secondary_hex, logo_url }`.
- `GET /branding/logo` (public) → raw bytes with `Content-Type` header. Split logo to its own route (avoids base64-bloating the JSON payload on every player navigation; the `<img>` hits the dedicated route).

Wire all four in `app/main.py` via `app.include_router(...)` (the established pattern; KPI + tenant-config under the admin prefix, branding public).

### Pattern: Admin write router (mirror `app/wallet/admin_router.py`)
- `prefix="/api/v1/admin/..."`, `Depends(current_active_admin)` on every endpoint.
- **`from __future__ import annotations` MUST be ABSENT** in router files (FastAPI's Python-3.13 `Annotated[T, Depends(...)]` resolver breaks with forward-ref strings → params misread as query params → 422). This is documented in every existing router. `[VERIFIED: app/wallet/admin_router.py, app/markets/router.py, app/bets/router.py headers]`
- `Annotated[User, Depends(current_active_admin)]` + `Annotated[AsyncSession, Depends(get_async_session)]`.
- Pydantic request schema with `ConfigDict(extra="forbid")` (reject stray fields → 422), mirroring `RechargeRequest`/`BanRequest`.
- Audit admin mutations: `AuditService.record(session, actor=f"user:{admin_id}", event_type="admin.branding_updated", payload={...})` then `session.commit()`. Capture `admin.id` as a plain value early (the MissingGreenlet trap documented in `wallet/admin_router.py`).

### Pattern: money-as-string response (reuse `MoneyStr`)
Import `from app.wallet.schemas import MoneyStr` and type every Decimal field as `MoneyStr`. `app/admin/schemas.py` already does this — copy that exact import. The `scripts/lint_money_columns.py` CI gate + a money-lint enforce string serialization. `[VERIFIED: app/admin/schemas.py]`

### Pattern: Server-Component fetch (mirror `frontend/src/lib/api.ts`)
- `apiBase()` resolves `BACKEND_URL` (SSR, Docker-internal) vs `NEXT_PUBLIC_API_URL` (browser). Reuse it.
- `fetch(url, { cache: "no-store" })` for fresh-per-render. Typed error throw on `!res.ok`.
- The dashboard page and the player root layout both fetch this way. **Admin KPI fetch needs the Bearer token** — the admin surface is Bearer-gated; the existing admin pages already forward the admin token (check `frontend/src/app/admin/users` for the established token-forwarding pattern when planning).

### Pattern: Recharts chart (mirror `frontend/src/components/price-history-chart.tsx`)
- `"use client"` chart component, `<ResponsiveContainer width="100%" height="100%">` inside a **fixed-height parent** (`h-64`) — ResponsiveContainer collapses to 0 without a sized parent (the documented Phase 9 pitfall).
- Empty state at the **same height** to avoid layout jump (mirror `ChartEmptyState`).
- `react-is` stays pinned via `pnpm.overrides` — do NOT change it or Recharts renders blank on React 19.
- Area vs line is discretion; an `AreaChart` reads better for cumulative volume. Use `--brand-primary` for the stroke/fill so the chart re-skins with branding (nice demo touch; optional).

### Pattern: runtime theming (extend `globals.css` + root layout)
Current `globals.css`: `:root { --background; --foreground; }` + `@theme inline { --color-background: var(--background); ... }`. Add brand tokens:
```css
:root { --brand-primary: #4f46e5; --brand-secondary: #0ea5e9; }  /* fallback defaults */
@theme inline {
  --color-brand-primary: var(--brand-primary);
  --color-brand-secondary: var(--brand-secondary);
}
```
Then in `frontend/src/app/layout.tsx` (make it `async`), `await fetchBranding()` and render a `<style>` block in `<head>`/before children:
```tsx
<style>{`:root{--brand-primary:${b.primary_hex};--brand-secondary:${b.secondary_hex};}`}</style>
```
Because the layout is a Server Component fetched per navigation (`cache: "no-store"`), a palette change in admin applies on next navigation with **no rebuild** (SC#5). Brand name + `<img src="/branding/logo">` consumed from the same payload. **Security:** the hex values are injected into a `<style>` tag — server-side hex validation (`^#[0-9a-fA-F]{6}$`) is what prevents CSS/`<style>` injection; never inject an unvalidated string (see threat model).

### Anti-Patterns to Avoid
- **Computing house P&L from `house_*` account balances.** Balances mix player-funding with settlement; must filter by transfer `kind` (see Flagged Unknown 1).
- **DAU from logins only.** Bets emit no audit event; logins-only undercounts bettors. UNION with `bets` (Flagged Unknown 2).
- **Using `markets.volume`/`volume_24hr` for the 24h bet-volume card.** Those are Polymarket replication fields, not internal stakes.
- **Money as JSON float anywhere.** Always `MoneyStr`. The CI money-lint will fail otherwise.
- **`from __future__ import annotations` in a router file.** Breaks FastAPI dependency resolution on 3.13.
- **Injecting unvalidated hex into the `<style>` block.** XSS/CSS-injection vector — validate server-side first.
- **A second Alembic head.** Chain the migration off `0008_phase8_user_created_at` (the single current head).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Money serialization | Custom Decimal→str | `app.wallet.schemas.MoneyStr` | Enforced by CI lint; project contract `[VERIFIED]` |
| Pagination envelope (if any list view) | Custom paginator | `app.markets.schemas.PaginatedResponse` / `paginated_response` | Project standard `[VERIFIED]` |
| Admin auth | New gate | `current_active_admin` (`fastapi_users_admin.current_user(active=True, superuser=True)`) | The single admin gate, reused since Phase 4 `[VERIFIED: app/auth/admin_router.py:89]` |
| Audit writes | Raw `INSERT INTO audit_log` | `AuditService.record(...)` | The sole allowed writer; commits atomically with the action `[VERIFIED]` |
| Ledger reads for P&L | New SUM logic bypassing the ledger | Query `entries`+`transfers` (read-only) | The ledger is the source of truth; never recompute balances elsewhere |
| Image content-type sniffing | Hand-rolled magic-byte parser | Python stdlib `imghdr` is deprecated (3.13); use the `Pillow`-free approach: validate the declared `Content-Type` against an allowlist + check the leading magic bytes manually for PNG/JPEG/WebP, and treat SVG as text/xml with a size cap | Don't add Pillow just for a sniff; a small magic-byte check + allowlist is enough for the demo. SVG is text — sanitize or restrict (see threat model). |
| Hex validation | Loose regex in JS only | Server-side `^#[0-9a-fA-F]{6}$` (pydantic validator / `Field(pattern=...)`) as source of truth; zod mirror for UX | SC#4 + the `<style>`-injection guard |
| Chart downsampling | Client-side bucketing | Server-side `date_trunc('day', ...)` GROUP BY | ≤30 points; no downsampling needed (D-01) |

**Key insight:** This phase is almost entirely *composition of existing primitives*. The risk is not "missing a library" — it's transcribing the two wrong SC formulas. Resolve those against the code (done above) and the rest is pattern-mirroring.

---

## Common Pitfalls

### Pitfall 1: Copying SC#2's `SUM(house_revenue) - SUM(house_expense)`
**What goes wrong:** there is no `house_expense` account; the query errors or (worse) someone invents an account and the ledger invariant breaks.
**How to avoid:** use the kind-filtered net-flow query (Flagged Unknown 1). Net `settle_loss` credits to `house_revenue` minus `settle_winnings` debits from `house_promo`, with `reverse_*` netted.
**Warning sign:** any SQL referencing a `house_expense` kind/account.

### Pitfall 2: DAU from the audit log alone
**What goes wrong:** bettors who didn't re-login are invisible; DAU silently undercounts; a demo with active bets shows a low DAU.
**How to avoid:** UNION `bets` + `auth.session_started`. Parse `actor` `user:<uuid>`.
**Warning sign:** DAU query touches only `audit_log`; or it references the non-existent `auth.login_started` event.

### Pitfall 3: Wrong event-type name for logins
**What goes wrong:** filtering `audit_log` on `auth.login_started`/`auth.login_*` returns zero rows — that event is never emitted (it's only in the stale `KNOWN_EVENT_TYPES` dropdown list).
**How to avoid:** the emitted player-login event is **`auth.session_started`** (`app/auth/router.py:176`). Admin is `auth.admin_login_started`.

### Pitfall 4: Recharts blank on React 19 / 0-height container
**What goes wrong:** chart renders blank (react-is mismatch) or invisible (ResponsiveContainer in an unsized parent).
**How to avoid:** keep `react-is` pinned via `pnpm.overrides`; wrap in a fixed-height (`h-64`) parent. A "chart not blank" smoke test is the sentinel (Phase 9 precedent).

### Pitfall 5: `<style>`-block CSS injection via unvalidated hex
**What goes wrong:** an admin (or a compromised admin path) stores `}</style><script>…` as a "color"; it renders into every player page.
**How to avoid:** server-side validate `primary_hex`/`secondary_hex` against `^#[0-9a-fA-F]{6}$` before persist AND before injection. Reject with a clear 422.

### Pitfall 6: Second Alembic head
**What goes wrong:** the migration branches and `alembic upgrade head` ambiguates; CI single-head check fails.
**How to avoid:** `down_revision = "0008_phase8_user_created_at"`. Confirmed current single head (chain: 0001→0002→0003→[0004_markets & 0004_polymarket]→0005→**0006_merge**→0007→**0008** head). `[VERIFIED: down_revision chain]`

### Pitfall 7: Logo bloats every player navigation
**What goes wrong:** returning base64 logo in `GET /branding/current` ships the image on every SSR navigation.
**How to avoid:** keep `/branding/current` JSON small (name + 2 hexes + a `logo_url` string); serve bytes from the dedicated `GET /branding/logo` route that the browser `<img>` caches.

### Pitfall 8: Timezone drift on "today"
**What goes wrong:** "house P&L today" / "24h volume" boundaries differ between server timezone and display.
**How to avoid:** all `created_at`/`occurred_at` are `timezone=True`. Pick one timezone (UTC unless project says otherwise) for `date_trunc('day', ...)`; document it.

---

## Code Examples

### Admin KPI aggregate (ORM, money-as-string)
```python
# Source pattern: app/wallet/service.get_transactions (entries+transfers join) + app/admin
from sqlalchemy import func, select, case
from app.wallet.models import Entry, Transfer
from app.wallet.constants import HOUSE_REVENUE_ACCOUNT_ID, HOUSE_PROMO_ACCOUNT_ID

async def house_pnl(session, *, lo=None, hi=None) -> Decimal:
    revenue = func.coalesce(func.sum(case(
        (Transfer.kind == "settle_loss", Entry.amount),
        (Transfer.kind == "reverse_loss", -Entry.amount),
        else_=0)), 0)
    expense = func.coalesce(func.sum(case(
        (Transfer.kind == "settle_winnings", Entry.amount),
        (Transfer.kind == "reverse_winnings", -Entry.amount),
        else_=0)), 0)
    stmt = (select((revenue - expense).label("pnl"))
            .select_from(Entry).join(Transfer, Entry.transfer_id == Transfer.id)
            .where(Transfer.kind.in_(
                ("settle_loss","reverse_loss","settle_winnings","reverse_winnings"))))
    if lo is not None: stmt = stmt.where(Entry.created_at >= lo)
    if hi is not None: stmt = stmt.where(Entry.created_at < hi)
    return (await session.execute(stmt)).scalar_one()  # Decimal -> MoneyStr in schema
```

### DAU UNION count (ORM)
```python
from datetime import timedelta, datetime, UTC
from sqlalchemy import func, select, cast, literal
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.bets.models import Bet
from app.core.audit.models import AuditLog

async def dau(session, *, window_hours: int) -> int:
    lo = datetime.now(UTC) - timedelta(hours=window_hours)
    bettors = select(Bet.user_id).where(Bet.created_at >= lo)
    logins = (select(cast(func.split_part(AuditLog.actor, ":", 2), PG_UUID))
              .where(AuditLog.event_type == "auth.session_started",
                     AuditLog.occurred_at >= lo,
                     AuditLog.actor.like("user:%")))
    active = bettors.union(logins).subquery()          # UNION dedups
    return (await session.execute(select(func.count()).select_from(active))).scalar_one()
```

### SC#6 negative test (mirror `tests/admin/test_auth_negative.py`)
```python
# A player Bearer (is_superuser=False) -> 403 on /admin/tenant-config (GET + PUT).
# Reuse tests.admin._helpers (seed_user, auth, client, ADMIN_PASSWORD, cleanup_user).
# If admin login itself rejects the player (no admin Bearer for non-superuser),
# that 400/401 wall is acceptable per the existing test's branch.
```

---

## Project Constraints (from CLAUDE.md)

- **PHASES.md workflow is mandatory.** Read PHASES.md first; if Phase 10 is not `⬜ Not started`, STOP. Mark `🔄 In progress` + owner + branch `gsd/phase-10-...` and commit before code. (This is the orchestrator's job, not research's, but the plan must respect it.)
- **Money discipline:** `NUMERIC(18,4)` + `Decimal` from strings; serialize as `MoneyStr`. CI money-lint enforces.
- **Single Alembic head invariant:** chain off `0008_phase8_user_created_at`.
- **`tenant_id` ghost column on every new table** (`tenant_config` included), `default=lambda: get_settings().TENANT_ID_DEFAULT`.
- **`from __future__ import annotations` NOT used in router files.**
- **Per-phase branch, 1 PR per phase, never commit to `main`.** Gates (`plan_check`, `verifier`, `code_review`) mandatory.
- **Spanish for conversation, English for code/paths.** `python` bare is broken on this Windows box — use venv (`.venv/Scripts/python.exe`).

---

## Runtime State Inventory

This phase is **additive greenfield within a brownfield repo** — it creates a new table and new endpoints; it does **not** rename or migrate existing runtime state. The five categories:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None renamed. New: `tenant_config` single row (seeded with default branding by the migration or a startup default). | Migration creates table + seeds one row (mirror the migration-0003 `house_*` singleton seed pattern). |
| Live service config | None — no external service stores Phase 10 state. Branding lives entirely in the new DB row. | None. |
| OS-registered state | None — no Task Scheduler / cron / systemd units involved. | None — verified (this phase adds no scheduled jobs; KPIs compute on-demand per D-01). |
| Secrets/env vars | Reuses existing `BACKEND_URL` / `NEXT_PUBLIC_API_URL` (frontend) and `TENANT_ID_DEFAULT` (backend settings). No new secrets. | None. |
| Build artifacts | Frontend: `globals.css` + root `layout.tsx` change — no rebuild needed for branding *values* (runtime fetch), but the new CSS tokens require the normal Next build. No stale egg-info / compiled artifacts. | Standard `next build` picks up the new tokens; branding values are runtime, not built-in. |

**Single-row enforcement (the one stateful design choice):** enforce one `tenant_config` row via a fixed PK (e.g. seed a known UUID, or a `CHECK`/partial-unique on a constant column). Recommended: a `tenant_id` ghost + a `UNIQUE` on `tenant_id` so v2 multi-tenant becomes "one row per tenant" naturally — the documented single-tenant→multi-tenant seam (D-07).

---

## Validation Architecture

> `workflow.nyquist_validation` not found disabled — section included.

### Test Framework
| Property | Value |
|----------|-------|
| Backend framework | pytest + pytest-asyncio (`@pytest.mark.integration`, `@pytest.mark.asyncio(loop_scope="session")`), testcontainers Postgres |
| Backend config | `backend/pytest.ini`/`pyproject` (existing); tests under `backend/tests/` with `tests/admin/_helpers.py` (`seed_user`, `auth`, `client`, `ADMIN_PASSWORD`, `cleanup_user`) |
| Frontend framework | Vitest + @testing-library/react + jsdom |
| Quick run (backend) | `.venv/Scripts/python.exe -m pytest backend/tests/admin -x` (Windows venv per CLAUDE.md) |
| Quick run (frontend) | `pnpm --dir frontend test` (vitest run) |
| Full suite | backend `pytest` + frontend `vitest run` (note: ~18 unit failures pre-exist locally with no Postgres — integration tests need the testcontainer) |

### Phase Requirements → Test Map
| Req | Behavior | Test Type | Automated Command | File Exists? |
|-----|----------|-----------|-------------------|--------------|
| ADD-01 | Login lands on `/admin` dashboard; sessionStorage default-route flag | frontend unit / manual | `pnpm --dir frontend test` | ❌ Wave 0 |
| ADD-02 | KPI endpoint returns 5 cards w/ correct values (money as string) | integration | `pytest backend/tests/admin/test_kpi.py -x` | ❌ Wave 0 |
| ADD-02 (P&L) | `settle_loss` − `settle_winnings` net = expected; reversal nets to 0 | integration | `pytest backend/tests/admin/test_kpi.py::test_house_pnl -x` | ❌ Wave 0 |
| ADD-02 (DAU) | distinct(bettors ∪ logins) over window; admin logins excluded | integration | `pytest backend/tests/admin/test_kpi.py::test_dau -x` | ❌ Wave 0 |
| ADD-02 (pending) | markets `deadline<now` & not finalized counted | integration | `...::test_pending_resolutions -x` | ❌ Wave 0 |
| ADD-03 | 30-day daily buckets; synthetic fixture renders; chart not blank | frontend unit + smoke | `pnpm --dir frontend test` | ❌ Wave 0 |
| ADD-05 | `tenant_config` PUT persists; rejects bad hex (422) + oversized logo | integration | `pytest backend/tests/admin/test_tenant_config.py -x` | ❌ Wave 0 |
| ADD-06 | `GET /branding/current` public; palette change reflects in `<style>` | integration + manual | `pytest backend/tests/branding/test_branding_public.py -x` | ❌ Wave 0 |
| SC#6 | player Bearer → 403 on `/admin/tenant-config` (GET+PUT) | integration | `pytest backend/tests/admin/test_tenant_config_negative.py -x` | ❌ Wave 0 (mirror `test_auth_negative.py`) |

### Test Seams (what to validate, how)
- **House P&L:** seed bets → resolve via `SettlementService.resolve_market` → assert the KPI query equals (Σ loser stakes) − (Σ winner net winnings). Then `reverse_settlement` → assert P&L returns to the pre-settlement value (the `reverse_*` netting). Single-row imbalance (more losers) → positive P&L; all-winners → negative P&L. **This is the highest-value test** — it guards the corrected formula.
- **DAU:** seed (a) a user who only bet, (b) a user who only logged in (`auth.session_started`), (c) a user who did both → assert count = 3 (UNION dedups). Seed an admin login → assert it's NOT counted. Vary `window=24h|7d|30d`.
- **Pending resolutions:** seed markets with past/future `deadline` × `status` matrix → assert only past-deadline non-finalized counted; DRAFT excluded.
- **Branding validation:** PUT with `primary_hex="red"` → 422; PUT with a >256KB logo → 422 with a clear message; PUT with `Content-Type` not in allowlist → 422. PUT valid → `GET /branding/current` reflects it.
- **Runtime theming:** integration assert `/branding/current` payload; frontend test asserts the `<style>` block contains the validated hex (and that an injection attempt was rejected upstream). Manual: swap palette in admin, navigate a player page, observe re-skin (SC#5).
- **403 negative:** mirror `tests/admin/test_auth_negative.py` `_routes()` list with the new tenant-config routes.

### Sampling / observability for KPI queries
- Per task commit: `pytest backend/tests/admin -x` (fast integration subset).
- Per wave merge: full backend + frontend suites.
- Phase gate: full suite green before `/gsd-verify-work`.
- **Observability:** structlog is in the stack; log the KPI endpoint's total query time at INFO. D-01 says revisit caching only if a query measurably drags render — so emit the timing to make "measurably" observable. Sentry captures errors (existing). No new alert rules (Phase 11 tunes alerts).

### Wave 0 Gaps
- [ ] `backend/tests/admin/test_kpi.py` — covers ADD-02 (all five cards, P&L net, DAU UNION, pending predicate)
- [ ] `backend/tests/admin/test_tenant_config.py` + `test_tenant_config_negative.py` — ADD-05 + SC#6
- [ ] `backend/tests/branding/test_branding_public.py` — ADD-06 public endpoints + logo serving
- [ ] `backend/tests/admin/_helpers.py` — extend if a synthetic-bet seeder is needed for the 30-day fixture
- [ ] `frontend/src/components/*-kpi*.test.tsx` + volume-chart smoke test (mirror `price-history-chart.test.tsx`)
- [ ] 30-day synthetic bet fixture (seed script or test fixture) for chart render verification

---

## Security Domain

> `security_enforcement` not disabled — section included.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Reuse `current_active_admin` Bearer; no new auth surface. |
| V3 Session Management | partial | sessionStorage default-route flag is a UX hint, NOT a trust boundary — never gate auth on it. |
| V4 Access Control | yes | Every `/admin/*` endpoint gated by `current_active_admin`; `/branding/*` is intentionally public (read-only branding). SC#6 negative test enforces 403 for players. |
| V5 Input Validation | yes | Server-side hex regex (`^#[0-9a-fA-F]{6}$`), logo size cap + content-type allowlist; pydantic `extra="forbid"`. |
| V6 Cryptography | no | No new crypto; reuse existing JWT/Argon2 stack. |
| V12 Files/Resources | yes | Logo upload: size cap (≤256KB), content-type allowlist (PNG/JPEG/WebP/SVG), magic-byte sanity check; SVG treated as untrusted markup. |

### Known Threat Patterns for {FastAPI admin + runtime CSS theming}
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Stored CSS/HTML injection via unvalidated hex into `<style>` | Tampering / Elevation | Server-side hex allowlist regex BEFORE persist and BEFORE injection; reject 422. |
| Malicious SVG logo (script in SVG served same-origin) | Elevation (XSS) | Serve logo with a strict `Content-Type`, `Content-Disposition`/`X-Content-Type-Options: nosniff`; prefer rendering via `<img>` (SVG-in-`<img>` does not execute script) — never inline untrusted SVG into the DOM. Consider restricting SVG or sanitizing if inlined. |
| Logo upload DoS (huge file) | Denial of Service | Hard size cap (≤256KB) enforced server-side before reading the full body where possible; reject 413/422. |
| Decompression / image bomb | DoS | Size cap + content-type allowlist; magic-byte check; avoid expensive image processing (no resizing in v1). |
| Player reaching admin KPI/tenant-config | Elevation | `current_active_admin` on every admin endpoint; SC#6 negative test (player Bearer → 403). |
| KPI endpoint leaking PII | Info Disclosure | KPIs are aggregates/counts only — no per-user rows; DAU returns a count, not ids. Keep it that way. |
| Branding endpoint enumeration | Info Disclosure | `/branding/current` is intentionally public and contains only operator-chosen branding — no sensitive data; acceptable. |

The planner's `<threat_model>` MUST cover: hex `<style>` injection, SVG/logo upload (content-type + size + magic bytes), and the admin/player access boundary on the new endpoints.

---

## State of the Art

| Old (CONTEXT/ROADMAP assumption) | Reality in code | Impact |
|----------------------------------|-----------------|--------|
| `SUM(house_revenue) - SUM(house_expense)` | No `house_expense` account; net `settle_loss` − `settle_winnings` by kind | Plan must use the corrected query. |
| DAU from audit `auth.login_*` | No `auth.login_*` event; login event is `auth.session_started`; bets emit NO audit event | UNION bets + `auth.session_started`. |
| Next.js 15 (CONTEXT) | Next.js `^16.2.6` | Confirm App Router APIs against 16 in plans. |
| Mirrored markets have `endDate` column | Only `markets.deadline` exists (Phase 6 added no end-date) | Pending-resolutions predicate uses `deadline` for both sources. |

**Deprecated/outdated:** `KNOWN_EVENT_TYPES` in `app/core/audit/schemas.py` is a hardcoded dropdown list that overstates emitted events (`bet.placed`, `auth.login_started`, `settlement.completed` are listed but the actual emitted names differ — settlement emits `settlement.resolved`/`settlement.reversed`, login emits `auth.session_started`, bets emit nothing). Trust the emitting code, not this list. (Optional: this phase could extend the list with `admin.branding_updated` for the audit viewer dropdown — nice-to-have, not required.)

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | "Today" boundary = UTC midnight (project default) | House P&L / DAU | Off-by-a-timezone on "today" cards; planner must confirm the app's display timezone. LOW risk, easy to change. |
| A2 | DAU excludes admin logins (players only) | DAU | DAU slightly inflated if admins counted; a one-line filter. Recommend excluding. |
| A3 | Pending-resolutions excludes DRAFT markets | Pending resolutions | A never-opened market with a past placeholder deadline would be miscounted; recommend excluding DRAFT. LOW. |
| A4 | 256KB logo cap + PNG/JPEG/WebP/SVG allowlist (CONTEXT example values) | Branding | These are CONTEXT example values (D-08 said "e.g. ≤256KB"); the operator may want a different cap/allowlist. Confirm at plan time. |
| A5 | An index on `bets(created_at)` / `audit_log(occurred_at)` is not yet present | DAU/volume cost | At demo volumes irrelevant; if data grows, add indexes. Did not verify index DDL exhaustively — `bets_user_idx` is on `user_id` only. |
| A6 | Admin pages already forward the Bearer token for server-side admin fetches | Server-Component fetch | The exact token-forwarding mechanism for admin SSR fetches was not read this session (only the public `lib/api.ts`); planner must read `frontend/src/app/admin/users` to confirm before wiring the KPI fetch. |

**These `[ASSUMED]` items need confirmation in planning/discuss before becoming locked decisions.**

---

## Open Questions

1. **Admin SSR fetch auth (A6).**
   - What we know: the admin surface is Bearer-gated; `lib/api.ts` (public) uses `cache:"no-store"`.
   - What's unclear: how the *admin* Server Components obtain/forward the admin Bearer for `GET /admin/dashboard/kpis`.
   - Recommendation: read `frontend/src/app/admin/users/*` (Phase 8 admin pages) before planning the KPI fetch; mirror whatever token-forwarding it uses.

2. **"Today" timezone (A1).**
   - Recommendation: default UTC `date_trunc('day', now())`; confirm against CONVENTIONS.md/STATE.md.

3. **Single-row enforcement mechanism (D-07).**
   - Recommendation: seed one row with a fixed UUID PK + `UNIQUE(tenant_id)` (the multi-tenant seam). Planner picks the exact constraint.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Postgres (testcontainer) | Integration tests | ✓ (per project) | 16 | none — integration tests need it (local bare-metal Postgres absent per memory; testcontainer covers CI) |
| Python venv | Backend tests | ✓ | 3.12/3.13 | `.venv/Scripts/python.exe` (bare `python` broken on Windows) |
| pnpm + Node | Frontend build/tests | ✓ | Node 22 recommended | — |
| Redis | Not needed this phase (no caching per D-01) | n/a | — | — |
| Object storage / S3 | NOT used (logo is in-row) | ✗ (by design) | — | base64 bytes in `tenant_config` (D-08) |

**Missing with no fallback:** none blocking. **Missing with fallback:** object storage → in-row bytes (intentional v1 choice).

---

## Sources

### Primary (HIGH confidence — read this session)
- `backend/app/wallet/{constants,models,service}.py` — ledger schema, account kinds, `_post_transfer`
- `backend/app/settlement/{service,constants,payout}.py` — exact settlement money flows (the P&L source of truth)
- `.claude/skills/spike-findings-xpredict/references/settlement.md` — settlement model corroboration
- `backend/app/auth/{models,deps,router,admin_router}.py` — no last_seen column; `auth.session_started`; `current_active_admin` definition
- `backend/app/core/audit/{models,service,schemas,router}.py` — actor format, AuditService, stale KNOWN_EVENT_TYPES
- `backend/app/bets/{models,constants}.py` + grep — bets emit no audit event; stake/created_at
- `backend/app/markets/{models,enums}.py` + `alembic/versions/0004_phase6_polymarket_sync.py` — status/deadline/source; no end-date column
- `backend/alembic/versions/0006,0007,0008` — single-head chain (head = 0008)
- `backend/app/{admin/schemas,wallet/admin_router,db/types}.py` — MoneyStr, admin router pattern, Money alias
- `backend/tests/admin/test_auth_negative.py` — 403 negative-test pattern
- `frontend/{package.json, src/app/globals.css, src/app/layout.tsx, src/lib/api.ts, src/components/price-history-chart.tsx, src/app/admin/{page,layout}.tsx, src/components/admin/admin-nav.tsx}` — recharts/react-is wiring, theming hook, Server-Component fetch, admin shell
- `.planning/phases/10-.../10-CONTEXT.md`, `.planning/ROADMAP.md` §Phase 10 (SC#1–6), `.planning/REQUIREMENTS.md` (ADD-01/02/03/05/06), `CLAUDE.md`

### Secondary / Tertiary
- None — this is a brownfield phase resolved entirely against first-party code; no web sources needed (ROADMAP marks Recharts/CSS-vars as well-documented, no research needed).

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every dep verified present; zero new packages.
- House P&L derivation (Flagged 1): HIGH — traced through actual settlement code + constants.
- DAU source (Flagged 2): HIGH — confirmed no last_seen, no bet audit event, real login event name.
- Pending/active markets/volume predicates: HIGH — read models + enums + migration.
- Branding/theming patterns: HIGH — read globals.css, layout, api.ts, admin router.
- Timezone of "today": MEDIUM — assumed UTC, flagged for confirmation (A1).
- Admin SSR token forwarding: MEDIUM — not read this session, flagged (A6).

**Research date:** 2026-05-31
**Valid until:** ~2026-06-30 (stable brownfield codebase; revalidate only if phases 1-9 are refactored)
