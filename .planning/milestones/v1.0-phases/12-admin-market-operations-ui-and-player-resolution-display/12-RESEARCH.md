# Phase 12: Admin Market Operations UI & Player Resolution Display - Research

**Researched:** 2026-06-03
**Domain:** Frontend wiring (Next.js 15 App Router) over already-merged FastAPI backends + ONE additive backend migration
**Confidence:** HIGH (every claim grounded in the actual codebase; no greenfield speculation)

## Summary

Phase 12 is the **v1.0 closure phase**. The milestone audit (`.planning/v1.0-MILESTONE-AUDIT.md`, status `gaps_found`) found that ~10 requirements are "complete in isolation" — endpoints exist, are admin-gated, and are tested — but unreachable because **no frontend wires them into a flow**. This research confirms that diagnosis against source: the backend for ADM-01..04/07, ADM-05/06, STL-02/07 is fully present and tested; the only genuine *code* gap is STL-06 (the winning outcome is never persisted to a queryable column), and BET-06 (per-market stake limits never built — only global constants).

The work decomposes into **four thin vertical slices** plus one cross-cutting backend change:
1. **Resolution-display slice (STL-06)** — the only slice with a backend change: a `0010` migration adds `winning_outcome_id` / `resolution_source` / `resolution_justification` to `markets`; `mark_resolved` persists them inside the existing settlement transaction; `get_market_public` stops 404ing RESOLVED markets; `MarketRead` exposes the fields; the player market-detail page gets a RESOLVED branch.
2. **Market-CRUD slice (ADM-01..04, ADM-07)** — a new `/admin/markets` page (clone of `/admin/users`) + create/edit/close forms (clone of `/admin/branding`), all wired to the EXISTING `admin_market_router`.
3. **Resolve/reverse/force-settle slice (STL-02, STL-07, ADM-05, ADM-06)** — two-step confirm dialogs (clone of `BanConfirmDialog`) wired to the EXISTING settlement endpoints; the KPI "pending resolutions" card deep-links here.
4. **Per-market-stake-limits slice (BET-06)** — add min/max columns to `markets` (recommended over TenantConfig — see Q7), an admin form field, and wire both client- and server-side enforcement points.

**Primary recommendation:** Treat this as integration work, not construction. For every endpoint, the request/response schema already exists — clone the nearest existing page/component (this doc names the exact file for each) rather than inventing new patterns. The single highest-risk item is the `MarketResolvePort` signature change for STL-06 (it ripples to the Protocol, its real adapter, the auto-resolution caller, and every test fake) — plan it as one atomic task.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Persist winning outcome on resolve (STL-06) | API / Backend (`settlement` + `markets` model + migration) | — | Winner must be a queryable column, written in the settlement ACID tx; audit-log-only is the current gap |
| Expose resolution fields publicly (STL-06) | API / Backend (`MarketRead` + `get_market_public`) | — | The player read surface currently 404s RESOLVED markets |
| Render resolution display (STL-06) | Frontend Server Component (`/markets/[slug]`) | Backend (player payout from `/bets/me/portfolio`) | The detail page composes the public market read + the player's own settled position |
| Admin market list/create/edit/close (ADM-01..04/07) | Frontend (`/admin/markets`) | API / Backend (`admin_market_router`, already complete) | Pure UI wiring; backend mounted + tested |
| Resolve/reverse/force-settle (STL-02/07, ADM-05/06) | Frontend (two-step confirm dialogs) | API / Backend (`settlement_admin_router`, already complete) | Two-step confirm + mandatory justification is a client concern; backend enforces `min_length=1` |
| Per-market stake limits (BET-06) | API / Backend (`markets` columns + `bets` validation) | Frontend (admin form field + order-form zod) | Limits must be server-authoritative; client mirror is UX-only |
| Admin auth on all admin surfaces | API / Backend (`current_active_admin` Bearer) | Frontend (`"use server"` Bearer-forward lib) | Established pattern; `admin_jwt` HttpOnly cookie never reaches client JS |

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| STL-06 | Player sees resolution display: winning outcome, source ("Polymarket UMA"/"Operator: {name}"), justification, settlement timestamp, own payout/loss | Q1, Q2, Q3 — migration `0010` + `mark_resolved` persist + `MarketRead` fields + `get_market_public` fix + detail-page RESOLVED branch + portfolio payout |
| ADM-01 | Admin paginated market list with source/status/category filters | Q4, Q5 — `GET /api/v1/admin/markets` (paginated+filtered, tested) + clone `UsersDataTable` |
| ADM-02 | Admin create house market (question/criteria/deadline/50-50 odds/optional category) | Q4, Q5 — `POST /api/v1/admin/markets` (`MarketCreate`, tested) + clone `BrandingForm` |
| ADM-03 | Admin edit market odds/deadline/criteria while zero bets | Q4 — `PATCH /api/v1/admin/markets/{id}` (`MarketUpdate`, tested); NOTE deviation: only criteria locks after first bet |
| ADM-04 | Admin close market early (OPEN→CLOSED) | Q4 — `POST /api/v1/admin/markets/{id}/close` (tested) |
| ADM-05 | Admin resolve house market (= STL-02) | Q6 — `POST /admin/markets/{id}/resolve` (tested) + two-step confirm dialog |
| ADM-06 | Admin force-settle stuck Polymarket market (two-step + justification) | Q6 — `POST /admin/markets/{id}/force-settle` (tested) |
| ADM-07 | After first bet, criteria locked (UI disabled + API 423) | Q4 — API already returns 423 CRITERIA_LOCKED; UI disables the field when `bet_count > 0` |
| STL-02 | Admin resolve with mandatory justification + two-step confirm | Q6 — same endpoint as ADM-05; backend enforces `justification` `min_length=1` |
| STL-07 | Admin reverse settlement (compensating entries + justification) | Q6 — `POST /admin/markets/{id}/reverse` (tested); LANDMINE: re-resolve after reverse collides (Pitfall 5) |
| BET-06 | Per-market configurable min/max stake (replaces global-only) | Q7 — recommend columns on `markets`; wire `bets/router.py` + `order-entry-form.tsx` |

<user_constraints>
## User Constraints

**No CONTEXT.md exists for this phase** (`/gsd-discuss-phase` was not run; it is optional per CLAUDE.md "Skip discuss"). There are therefore no locked user decisions, discretion areas, or deferred ideas to copy verbatim. The binding constraints come from three sources instead:

### From the v1.0 Milestone Audit (`.planning/v1.0-MILESTONE-AUDIT.md`) — the design source
- This phase MUST close exactly the three blockers + BET-06, no scope creep. The audit's "Recommendation" section is the spec.
- STL-06 requires BOTH a backend data change (persist winner) AND the UI — fixing the UI alone is insufficient (audit BLOCKER-1).

### From ROADMAP.md Phase 12 success criteria (5 criteria — the acceptance gate)
- SC#5 is the integration gate: an operator creates a house market → a player bets → the operator resolves from the admin UI → the player sees the resolution display + realized P&L, **with no raw-API step anywhere**.

### From CLAUDE.md (project rules — same authority as locked decisions)
See `## Project Constraints (from CLAUDE.md)` below.
</user_constraints>

## Project Constraints (from CLAUDE.md)

| Directive | Source | Impact on Phase 12 |
|-----------|--------|--------------------|
| `PHASES.md` is the source of truth for who owns the phase; AI marks it In-progress before any code, In-review at PR | CLAUDE.md "Phase tracking" | Plan must include the PHASES.md bookkeeping steps (steps 1 + 6) |
| Per-phase branch `gsd/phase-12-{slug}`; never commit to `main`; 1 PR per phase | CLAUDE.md "Branches & PRs" | All work on the phase branch |
| Money: `NUMERIC(18,4)` + Python `Decimal` from strings; never float, never Postgres MONEY; money is a JSON STRING on the wire | CLAUDE.md memory + WAL-05 + CONVENTIONS | New `markets` stake-limit columns use `Mapped[Money]`; the new `MarketRead` fields + any payout field serialize as strings; frontend renders money via string ops (`formatMoney`), never `parseFloat` for storage |
| Python 3.12 + uv + Docker for backend; `pnpm` for frontend | CLAUDE.md "Environment" | Backend tests via uv venv; frontend via pnpm |
| GitHub MCP / `gh` for PRs; PAT via env var; repo stays secret-free | CLAUDE.md "Environment" | PR creation only |
| Spanish for conversation, English for code/paths/identifiers | CLAUDE.md memory | RESEARCH/PLAN technical content + all code in English (honored) |
| Bare `python` is a broken Store stub on this host | CLAUDE.md memory | Use `.venv/Scripts/python.exe` or `uv run` for any backend command |
| The money-column AST lint (`scripts/lint_money_columns.py`) fails any non-`Money` money annotation | Phase 1 / CONVENTIONS §1 | New stake-limit columns MUST be `Mapped[Money]` or the lint fails CI |

## Standard Stack

No new libraries are needed. Phase 12 reuses the exact stack already in the repo.

### Core (already installed — verified in source)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Next.js | `^15.5.18` | App Router frontend | Locked Phase 1 (`frontend/package.json`); Phase 8/9/10 admin pages built on it |
| React | `19.2.x` | UI runtime | Locked; `react-is` pinned to it (Phase 9) |
| TanStack Table | `v8` (`@tanstack/react-table`) | Admin list table | The `/admin/users` table pattern (`users-data-table.tsx`) — clone for `/admin/markets` |
| react-hook-form | `^7` + `@hookform/resolvers ^3.9.0` | Admin forms | `BrandingForm` / `recharge-form.tsx` pattern |
| zod | (installed) | Client-side schema mirror | UX-only validation; server is authoritative |
| shadcn/ui | (vendored in `components/ui`) | Dialog/Form/Input/Select/Table/Textarea/Card/Button | All present (`ls frontend/src/components/ui`); no install |
| FastAPI + SQLAlchemy 2.0 async + Alembic | 3.12 | Backend | Existing; STL-06 + BET-06 add one migration + model edits |

### Supporting (already present)
| Library | Purpose | When to Use |
|---------|---------|-------------|
| `sonner` (toast) | Success/failure feedback on admin actions | Mirror `BanConfirmDialog` (toast on resolve/reverse success) |
| `lucide-react` (`Loader2`) | Submit spinners | Every confirm dialog / form submit |
| `httpx` + `testcontainers` (backend dev deps) | Integration tests through the ASGI app | New settlement-persist + market-CRUD tests |
| `vitest` + `@vitejs/plugin-react` | Frontend unit tests (jsdom for `.tsx`, node for `.ts`) | New admin-api URL-contract tests + form tests |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Stake limits as `markets` columns | Stake limits as `TenantConfig` rows | ROADMAP/REQUIREMENTS say "per market via TenantConfig", but TenantConfig is a single-row global table (Q7) — per-MARKET limits do not belong there. Recommend columns on `markets`. See Q7 for the full evidence-based recommendation. |
| Clone `BanConfirmDialog` for two-step confirm | Build a new generic confirm component | The ban dialog already implements mandatory-reason + min-length + destructive button + spinner + stays-open-during-submit. Cloning is faster and consistent. |

**Installation:**
```bash
# NONE. No new packages. Verify with:
#   (frontend) pnpm install   # lockfile already has every dep
#   (backend)  uv sync        # no new backend deps
```

**Version verification:** Not applicable — no new packages are added in this phase. The Package Legitimacy Audit below documents this explicitly.

## Package Legitimacy Audit

> This phase installs **NO external packages**. Every library it uses is already pinned in `frontend/package.json` / `frontend/pnpm-lock.yaml` and `backend/pyproject.toml` / `backend/uv.lock`, vetted in Phases 1–11.

| Package | Registry | Disposition |
|---------|----------|-------------|
| (none — no installs this phase) | — | N/A |

**Packages removed due to slopcheck [SLOP] verdict:** none (no installs).
**Packages flagged as suspicious [SUS]:** none (no installs).

If a planner later decides a helper package is warranted (not anticipated), it must pass the Package Legitimacy Gate before install. As of this research, the slice is buildable with zero new dependencies.

## Architecture Patterns

### System Architecture Diagram

```
                        ┌─────────────────────── ADMIN (Bearer JWT) ───────────────────────┐
                        │                                                                    │
  Admin browser         │   Next.js Server Components / "use server" actions                 │
  /admin/markets  ──────┼──> admin-markets-api.ts  ──[admin_jwt HttpOnly cookie → Bearer]──┐ │
  (NEW page)            │     (NEW, clone admin-api.ts)                                     │ │
                        │                                                                    │ │
  Two-step confirm  ────┼──> resolve/reverse/force-settle actions ─────────────────────────┤ │
  dialogs (NEW)         │     (clone BanConfirmDialog UX)                                    │ │
                        └────────────────────────────────────────────────────────────────┬─┘ │
                                                                                           │   │
                                                                                           ▼   ▼
                                                              FastAPI (mounted, tested — NO new endpoints)
                                                              ┌──────────────────────────────────────────┐
   admin market CRUD ────────────────────────────────────────> admin_market_router  /api/v1/admin/markets │
   resolve/reverse/force-settle ─────────────────────────────> settlement_admin_router  /admin/markets/... │  ◄── DIFFERENT PREFIX (landmine)
                                                              │      └─> SettlementService.resolve_market   │
                                                              │            └─> MarketResolvePort.mark_resolved│  ◄── STL-06 CHANGE LANDS HERE
                                                              │                  (persist winner — NEW)      │
                                                              └──────────────────────────────────────────┘
                                                                                  │  (one ACID tx: payouts + status + winner + audit)
                                                                                  ▼
                                                                          Postgres  markets / outcomes / bets / accounts / entries / audit_log
                                                                          (migration 0010 adds 3 markets cols + 2 stake-limit cols)
                                                                                  ▲
                        ┌──────────────────── PLAYER (cookie) ─────────────────┐  │
   Player browser       │   Next.js Server Component  /markets/[slug]           │  │
   /markets/[slug] ─────┼──> fetchMarket(slug)  ──> public_market_router GET /{slug}  ── (STOP 404ing RESOLVED — fix)
   (RESOLVED branch NEW)│      + (NEW) read player's settled position from      │  │
                        │        /bets/me/portfolio for own payout/loss ────────┼──┘
                        └───────────────────────────────────────────────────────┘
```

The diagram's load-bearing facts: (1) the two admin routers live under **different path prefixes** (a documented landmine — see Pitfall 1); (2) the STL-06 backend change is confined to `mark_resolved` + the model + the public read schema; (3) the player payout for the resolution display comes from the existing portfolio endpoint, not a new one.

### Recommended Project Structure (new/changed files)
```
backend/app/
├── markets/
│   ├── models.py            # EDIT: add winning_outcome_id, resolution_source, resolution_justification, min_stake, max_stake to Market
│   ├── schemas.py           # EDIT: add the 3 resolution fields to MarketRead (+ min/max to MarketRead/MarketCreate/MarketUpdate for BET-06)
│   └── router.py            # EDIT: get_market_public — allow RESOLVED (line 164)
├── settlement/
│   ├── market_port.py       # EDIT: extend mark_resolved signature (resolution_source, justification) — Protocol
│   ├── adapters.py          # EDIT: HouseMarketResolveAdapter.mark_resolved persists the 3 fields
│   └── service.py           # EDIT: pass source + justification through to mark_resolved (and a 'POLYMARKET_UMA' vs admin source)
├── bets/
│   ├── service.py           # EDIT (BET-06): read per-market min/max via the market read port
│   ├── router.py            # EDIT (BET-06): per-market stake check replaces/augments the global one (lines 92-97)
│   └── market_port.py       # EDIT (BET-06): MarketView carries min_stake/max_stake
└── alembic/versions/
    └── 0010_phase12_*.py    # NEW: add_column x5 onto markets (down_revision = "0009_phase10_tenant_config")

frontend/src/
├── app/admin/markets/
│   ├── page.tsx             # NEW: Server Component, clone of app/admin/users/page.tsx
│   ├── new/page.tsx         # NEW (or a dialog): create-market form
│   └── [id]/page.tsx        # NEW: market detail/edit + resolve/reverse/force-settle actions
├── app/markets/[slug]/
│   └── page.tsx             # EDIT: add the RESOLVED branch (resolution display)
├── components/admin/
│   ├── markets-data-table.tsx   # NEW: clone users-data-table.tsx (TanStack v8, server-driven)
│   ├── market-form.tsx          # NEW: clone branding-form.tsx (RHF + zod)
│   ├── resolve-market-dialog.tsx# NEW: clone ban-confirm-dialog.tsx (mandatory justification)
│   ├── reverse-settlement-dialog.tsx # NEW: clone ban-confirm-dialog.tsx
│   └── force-settle-dialog.tsx       # NEW: clone ban-confirm-dialog.tsx
├── components/
│   └── market-resolution-panel.tsx   # NEW: STL-06 display block for /markets/[slug]
├── components/admin/admin-nav.tsx    # EDIT: turn the disabled "Markets" <span> into a real Link
└── lib/
    ├── admin-markets-api.ts     # NEW: "use server" Bearer-forward, clone admin-api.ts
    └── admin-markets-types.ts   # NEW: shared types ("use server" files export only async fns)
```

### Pattern 1: "use server" Bearer-forwarding API module
**What:** Every admin API call funnels through a `"use server"` module that reads the `admin_jwt` HttpOnly cookie server-side and forwards it as `Authorization: Bearer <token>`. The token never reaches client JS.
**When to use:** All admin market CRUD + resolve/reverse/force-settle calls.
**Example:**
```typescript
// Source: frontend/src/lib/admin-api.ts (lines 44-73) — clone verbatim for admin-markets-api.ts
"use server";
import { cookies } from "next/headers";

async function bearerHeader(): Promise<Record<string, string>> {
  const store = await cookies();
  const token = store.get("admin_jwt")?.value;
  if (!token) throw new Error("Not authenticated");
  return { Authorization: `Bearer ${token}` };
}

export async function adminApiFetch<T = unknown>(path, init?): Promise<T> {
  const auth = await bearerHeader();
  const res = await fetch(`${getBackendUrl()}${path}`, {
    method: init?.method, body: init?.body,
    headers: { ...(init?.headers ?? {}), ...auth },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json() as Promise<T>;
}
// NOTE: pass the FULL path. Market CRUD → "/api/v1/admin/markets". Settlement → "/admin/markets/{id}/resolve".
// This module already handles both prefixes (see rechargeWallet which uses /admin/wallets).
```

### Pattern 2: TanStack v8 server-driven admin list
**What:** A `"use client"` table with `manualPagination`/`manualSorting`, holding filter/sort/page state and refetching via the Server Action on every change. Search/filter resets to page 1. Has loading-skeleton, empty, and error states.
**When to use:** `/admin/markets` list (ADM-01). Columns: question, source badge, status badge, category, deadline, bet_count, created_at, "View".
**Example:** Clone `frontend/src/components/admin/users-data-table.tsx` (the whole file). Swap `fetchUsers`→`fetchMarkets`, the columns array, and the row-click target (`/admin/markets/{id}`). The filter bar swaps the status `Select` for source + status + category selects (backend filters: `source`, `status`, `category` — see Q4). Backend returns `PaginatedResponse[MarketListItem]` (`{items,total,page,page_size,pages}`).

### Pattern 3: RHF + zod admin form
**What:** `"use client"` + `useForm` + `zodResolver` + shadcn `Form`/`FormField`/`FormItem`/`FormControl`/`FormMessage` + `Loader2` submit spinner + sonner feedback. The zod schema mirrors the server contract for UX only; the server is authoritative. A 422 maps server field-errors to inline `FormMessage`.
**When to use:** Create-market + edit-market forms (ADM-02, ADM-03).
**Example:** Clone `frontend/src/components/admin/branding-form.tsx`. The create-market zod schema mirrors `MarketCreate` (Q4): `question` 1..500, `resolution_criteria` 1..2000, `deadline` future datetime, `initial_odds_yes` `(0,1)` default 0.5, `category` optional ≤100. The edit form mirrors `MarketUpdate` and DISABLES the `resolution_criteria` field when `bet_count > 0` (ADM-07).

### Pattern 4: Two-step confirm dialog with mandatory justification
**What:** A shadcn `Dialog` with a MANDATORY reason/justification `Textarea` (backend `min_length=1`, validated client-side before submit), a destructive confirm button with a spinner, the dialog stays open during submit (prevents double-click), toast on success, parent refetches.
**When to use:** Resolve (STL-02/ADM-05), reverse (STL-07), force-settle (ADM-06).
**Example:** Clone `frontend/src/components/admin/ban-confirm-dialog.tsx` (lines 59-76 are the validate-then-submit core). For RESOLVE, add an outcome `Select` (YES/NO from the market's outcomes) above the justification — that is the only structural addition over the ban dialog. The "two-step" requirement is satisfied by: the page has a "Resolve" button → opens the dialog (step 1: propose outcome + justification) → "Confirm resolve" submits (step 2: confirm). The endpoint receives the already-confirmed resolution.

### Pattern 5: STL-06 resolution display on the player detail page
**What:** A RESOLVED branch on `/markets/[slug]` rendering: winning outcome label, resolution source string, public justification, settlement timestamp, and (if the player is logged in and bet on it) their own payout/loss from the portfolio.
**When to use:** STL-06.
**Example:** Add to `frontend/src/app/markets/[slug]/page.tsx` (the existing Server Component). When `market.status === "RESOLVED"`, render a `MarketResolutionPanel` instead of the order-entry form. The player's own result comes from a server-side fetch of `/bets/me/portfolio` (forwarding the `xpredict_session` cookie, exactly as `portfolio/page.tsx` does) and filtering `settled` for `market_id === market.id` (see Q3).

### Anti-Patterns to Avoid
- **Inventing a new admin-API helper instead of cloning `admin-api.ts`.** The Bearer-forward + structured-error pattern is solved. Reuse it.
- **Hardcoding `/api/v1` on the settlement endpoints.** They live at `/admin/markets/{id}/resolve|reverse|force-settle` (NO `/api/v1`). See Pitfall 1.
- **Coercing money to a JS number anywhere.** Money is a string on the wire and must stay a string in storage/display (`formatMoney`). The KPI/portfolio code already models this — follow it.
- **Re-implementing settlement/idempotency logic.** The service is correct and tested. STL-06 only adds a column write inside the existing transaction; do not touch the ledger math.
- **Adding a user-identity field to any public read** (the activity feed deliberately omits it). The resolution display shows the *logged-in player's own* result, fetched via their own cookie-gated portfolio — never another user's.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Admin Bearer forwarding | A new cookie-reader | `adminApiFetch` pattern (`admin-api.ts`) | HttpOnly cookie + token-never-in-client-JS is already solved + tested |
| Server-driven paginated table | A custom table | Clone `users-data-table.tsx` (TanStack v8) | manualPagination/sorting + skeleton/empty/error states already built |
| Admin form with validation + 422 mapping | A bespoke form | Clone `branding-form.tsx` | RHF+zod+server-error-mapping pattern proven (Phase 10) |
| Two-step confirm + mandatory reason | A new dialog | Clone `ban-confirm-dialog.tsx` | Mandatory-reason + min-length + stays-open-during-submit proven (Phase 8) |
| Settlement / payout / idempotency | Any new ledger code | The existing `SettlementService` (untouched) | Tested, idempotent, ACID; STL-06 only persists one column |
| Money formatting | `parseFloat` + `toFixed` | `formatMoney` (`kpi-card.tsx`) / string ops | Float coercion violates the money-as-string mandate |
| Resolution audit trail | A new audit write | The existing `settlement.resolved` audit row | Already records winner/resolver/justification; STL-06 makes the winner *also* a queryable column |

**Key insight:** Phase 12's value is making existing, tested capabilities *reachable*. Almost every "new" file is a clone of a named existing file with the endpoint and fields swapped. The only genuinely new logic is the `0010` migration + the `mark_resolved` persist + the per-market stake check.

## Runtime State Inventory

> Phase 12 is NOT a rename/refactor/migration-of-existing-data phase. It is additive (new nullable columns + new UI). There is no stored string to rename, no live-service config to re-key, no OS-registered state. The one data-shape change is additive and backward-compatible. Inventory for completeness:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `markets` rows resolved BEFORE this phase have `resolved_at` set but the 3 new columns NULL (winner lives only in `audit_log`). | Code edit only for NEW resolutions. Existing RESOLVED markets will show a degraded resolution panel (no winning-outcome label) unless a one-time backfill from `audit_log.payload.winning_outcome` is added. **Recommend:** a small idempotent data backfill in the `0010` migration's `upgrade()` (UPDATE markets SET winning_outcome_id = (audit payload) WHERE status='RESOLVED'), OR accept that pre-Phase-12 demo markets are re-seeded. Flag for planner. |
| Live service config | None — no external service stores a Phase-12 string. | None — verified: no Datadog/n8n/Tailscale equivalents in this repo. |
| OS-registered state | None — verified: no Task Scheduler / pm2 / systemd registrations reference any Phase-12 identifier. | None. |
| Secrets / env vars | `BET_MIN_STAKE` / `BET_MAX_STAKE` remain valid as the GLOBAL DEFAULT (BET-06 makes per-market an override, not a replacement of the env vars). No secret renames. | None — keep the config constants as the fallback. |
| Build artifacts | None — no compiled artifacts carry a stale name; new columns are migration-driven. | None. |

**The canonical question — "after every file is updated, what runtime systems still have stale state?":** Only the historical `markets` rows that were resolved before the migration (winner-in-audit-only). Everything else is additive. This is the single item the planner must decide on (backfill vs re-seed demo data).

## Common Pitfalls

### Pitfall 1: The two admin routers use DIFFERENT path prefixes
**What goes wrong:** Calling `/api/v1/admin/markets/{id}/resolve` 404s, because resolve/reverse/force-settle are mounted WITHOUT the `/api/v1` prefix.
**Why it happens:** `admin_market_router` has `prefix="/api/v1/admin/markets"` (`markets/router.py` line 33) but `settlement_admin_router` has `prefix="/admin/markets"` (`settlement/router.py` line 46). Both are mounted in `main.py` (lines 195, 201).
**How to avoid:** Market CRUD → `/api/v1/admin/markets[...]`. Resolve/reverse/force-settle → `/admin/markets/{id}/resolve|reverse|force-settle`. This is the SAME class of bug already caught in UAT for the recharge endpoint and guarded by `frontend/src/lib/__tests__/admin-api.test.ts`. **Write the equivalent URL-contract test for the new market actions** (the planner should make this a Wave-0 / first-task guard).
**Warning signs:** A resolve action returns 404 "Not Found" / the Server Action surfaces a 500.

### Pitfall 2: `mark_resolved` discards the winner — the STL-06 root cause
**What goes wrong:** Even after adding columns, the winner stays NULL because `HouseMarketResolveAdapter.mark_resolved` only sets `status` + `resolved_at` (`settlement/adapters.py` lines 31-38).
**Why it happens:** The winner was only ever written to the `audit_log` (`settlement/service.py` lines 227-240). The model never had the columns.
**How to avoid:** (1) Add the columns to `Market`; (2) extend the `MarketResolvePort.mark_resolved` Protocol signature to accept `resolution_source` + `justification`; (3) update BOTH `HouseMarketResolveAdapter.mark_resolved` (persist all 3) and the `SettlementService.resolve_market` call site (it already has `justification`; it must derive `resolution_source` — `'POLYMARKET_UMA'` when `actor_user_id is None`/auto path, else the admin's display attribution). **Do this as ONE atomic task** — the Protocol change ripples to the real adapter, the auto-resolution path (Phase 7 calls the same service), and EVERY test fake (`FakeMarketResolver` in `test_settlement_router.py` line 84, plus `test_market_resolve_port.py`, `test_force_settle.py`, `test_resolve_market.py`).
**Warning signs:** `mypy` flags the Protocol mismatch; a fake's `mark_resolved` signature no longer conforms.

### Pitfall 3: `get_market_public` 404s RESOLVED markets — the second half of STL-06
**What goes wrong:** The player navigates to a resolved market and sees "Market not found" (the frontend `fetchMarket` throws `MarketNotFound` on the 404).
**Why it happens:** `get_market_public` (`markets/router.py` line 164) returns 404 unless `status in (OPEN, CLOSED)` — RESOLVED is excluded. The same guard exists in `MarketService.price_history` (line 345) and `recent_activity` (line 413).
**How to avoid:** Add `MarketStatus.RESOLVED.value` to the allowed set in `get_market_public`. Decide whether price-history/activity should also surface for RESOLVED markets (recommended yes, so the chart shows the full pre-resolution history). Add the resolution fields to `MarketRead` so the single read carries everything the panel needs.
**Warning signs:** A resolved market's detail page renders the not-found state.

### Pitfall 4: Money rendered as a float
**What goes wrong:** A payout like `140.0000` becomes `140` or loses precision.
**Why it happens:** Reflexively `parseFloat`-ing the string the backend sends.
**How to avoid:** Keep money a string end-to-end. Render with `formatMoney` (`kpi-card.tsx` lines 37-51) or the portfolio's `PnL` component (which reads the sign from the string). Any NEW backend money field (the BET-06 stake limits) MUST be `Mapped[Money]` (so the AST lint passes) and serialize as a string (mirror `MarketRead.serialize_volume_decimal`, schemas.py lines 108-111).
**Warning signs:** The money-column lint fails CI; a payout shows fewer than 4 decimals.

### Pitfall 5: Re-resolving a market AFTER a reversal collides on idempotency keys
**What goes wrong:** Resolve → reverse → resolve-again raises a `23505` and rolls back.
**Why it happens:** Documented in `settlement/constants.py` (lines 66-71): the second resolve reuses the original `settle:{bet_id}:{leg}` keys; the reversal does NOT free them. A per-bet settlement epoch is the (deferred) fix.
**How to avoid:** This is a KNOWN v1 limitation, not in scope to fix here. The reverse-settlement UI should set the right expectation: reversal restores the pre-settlement state for audit/correction; it does not yet support clean re-resolution. The planner should NOT promise "resolve again after reverse" in the UI copy. If a clean re-resolve is demanded, it's a separate backend task (add an epoch to the idempotency key) — flag, don't silently attempt.
**Warning signs:** A second resolve on a previously-reversed market 500s with a uniqueness violation.

### Pitfall 6: Resolver attribution string — house vs Polymarket
**What goes wrong:** A house-resolved market shows "Polymarket UMA" or vice-versa.
**Why it happens:** The resolution source must be derived correctly and the display must format two distinct strings: `"Operator: {admin_display_name}"` (house) vs `"Polymarket UMA"` (auto). The admin's `display_name` lives on the `User` model (`auth/models.py` line 52, nullable).
**How to avoid:** Persist `resolution_source` as a stable token (e.g. `"HOUSE"` / `"POLYMARKET_UMA"`) in the new column, derived in `resolve_market` from whether `actor_user_id` is set. For the house case, the display name must be resolved for the panel — EITHER persist the admin's display name into `resolution_justification`'s sibling at resolve time, OR look it up. **Recommendation:** persist a `resolution_source` token only; resolve the display name at read time is hard (the public read has no admin join). Simplest: store the attribution STRING the player should see (e.g. `"Operator: Jane"` or `"Polymarket UMA"`) — but that couples display to data. Cleaner: store `resolution_source` token + (for house) the resolving admin's `display_name` snapshot. Flag this small design choice to the planner; the audit row already has `resolver` (the admin UUID) for reference.
**Warning signs:** The panel shows a UUID instead of a name, or the wrong source.

## Code Examples

### Adding the resolution columns (mirror migration 0007 — the add_column pattern)
```python
# Source: backend/alembic/versions/0007_phase7_grace_period.py (verbatim shape)
# NEW FILE: backend/alembic/versions/0010_phase12_resolution_and_stake_limits.py
revision: str = "0010_phase12_resolution_and_stake_limits"
down_revision: str | None = "0009_phase10_tenant_config"   # current single head (verified)

def upgrade() -> None:
    op.add_column("markets", sa.Column("winning_outcome_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("markets", sa.Column("resolution_source", sa.String(40), nullable=True))
    op.add_column("markets", sa.Column("resolution_justification", sa.Text, nullable=True))
    # BET-06 (recommended: per-market columns) — Money == Numeric(18,4); NULL means "use global default"
    op.add_column("markets", sa.Column("min_stake", sa.Numeric(18, 4), nullable=True))
    op.add_column("markets", sa.Column("max_stake", sa.Numeric(18, 4), nullable=True))
    # (Optional) backfill winning_outcome_id for pre-Phase-12 RESOLVED markets from audit_log — see Runtime State Inventory.

def downgrade() -> None:
    for col in ("max_stake","min_stake","resolution_justification","resolution_source","winning_outcome_id"):
        op.drop_column("markets", col)
```

### Extending `mark_resolved` to persist the winner (the STL-06 core)
```python
# Source: backend/app/settlement/adapters.py (current lines 31-38) — EDIT
# Protocol (market_port.py) signature must change in lockstep, plus every test fake.
async def mark_resolved(
    self, session: AsyncSession, *, market_id: UUID,
    winning_outcome_id: UUID, resolution_source: str, justification: str,   # NEW params
) -> None:
    market = await session.get(Market, market_id)
    if market is None:
        raise NoResultFound(f"no market {market_id}")
    market.status = MarketStatus.RESOLVED.value
    market.resolved_at = datetime.now(UTC)
    market.winning_outcome_id = winning_outcome_id          # NEW — the gap fix
    market.resolution_source = resolution_source            # NEW — "HOUSE" | "POLYMARKET_UMA"
    market.resolution_justification = justification          # NEW — public trust signal
```

### Per-market stake enforcement (BET-06) at the existing server check
```python
# Source: backend/app/bets/router.py (current lines 92-97) — EDIT
# The MarketReadPort's MarketView gains min_stake/max_stake; the check prefers per-market, falls back to global.
settings = get_settings()
min_stake = market.min_stake if market.min_stake is not None else settings.BET_MIN_STAKE
max_stake = market.max_stake if market.max_stake is not None else settings.BET_MAX_STAKE
if not (min_stake <= body.stake <= max_stake):
    raise HTTPException(422, detail=f"Stake must be between {min_stake} and {max_stake}.")
# NOTE: `market` here comes from market_source.get_market(...) inside place_bet today; the router
# currently checks BEFORE calling the service. The planner must decide where the per-market limit
# is read (router needs the market; today only the service fetches it). Cleanest: move the limit
# check INTO BetService.place_bet right after the market is validated (service.py ~line 88).
```

### Player's own payout for the resolution display (STL-06)
```typescript
// Source pattern: frontend/src/app/portfolio/page.tsx loadPortfolio() (lines 65-83)
// In /markets/[slug]/page.tsx, when status === "RESOLVED" and a session cookie exists:
const store = await cookies();
const session = store.get("xpredict_session")?.value;
let myResult: SettledPosition | null = null;
if (session) {
  const res = await fetch(`${apiBase()}/bets/me/portfolio`, {
    headers: { Cookie: `xpredict_session=${session}` }, cache: "no-store",
  });
  if (res.ok) {
    const data = await res.json();
    myResult = (data.settled ?? []).find((p) => p.market_id === market.id) ?? null;
  }
}
// myResult.won / myResult.payout / myResult.realized_pnl feed the panel (all strings — render via formatMoney).
```

## State of the Art

| Old Approach (pre-Phase-12) | Current Approach (Phase 12) | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Winner persisted only in `audit_log` (admin-gated) | Winner also a queryable `markets.winning_outcome_id` column | This phase (STL-06) | Public read can show the resolution |
| `get_market_public` 404s RESOLVED markets | RESOLVED markets are publicly readable | This phase | Player resolution display becomes reachable |
| Stake limits global-only (`BET_MIN/MAX_STAKE` config) | Per-market override columns, global as fallback | This phase (BET-06) | Operator can set limits per market |
| Admin market ops via raw API/curl only | Admin market ops via `/admin/markets` UI | This phase (ADM-*) | Operator-ready demo |

**Deprecated/outdated:** Nothing is removed. The global stake-limit env vars stay as the default. The audit row stays the system of record for the full resolution event; the new columns are a *denormalized, publicly-readable* projection of it.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | BET-06 is best modeled as columns on `markets`, NOT TenantConfig rows | Q7 / Standard Stack | Low — ROADMAP/REQUIREMENTS *say* "TenantConfig", but TenantConfig is structurally single-row global (verified). If the planner insists on TenantConfig, per-market semantics don't fit; recommend confirming with Pol. This is the one place research diverges from the requirement TEXT on evidence. |
| A2 | `resolution_source` should be a stable token (`"HOUSE"`/`"POLYMARKET_UMA"`) with display formatting in the frontend | Pitfall 6 / Q3 | Low — the alternative (store the full display string) couples data to copy. Either works; flagged for planner. |
| A3 | Pre-Phase-12 RESOLVED markets need a backfill (or re-seed) to show a complete resolution panel | Runtime State Inventory | Medium — if skipped, historical resolved markets show a degraded panel (no winner label). For a fresh demo this is moot; for an existing DB it matters. Planner must decide. |
| A4 | The per-market stake check should move into `BetService.place_bet` (the service fetches the market; the router does not) | Code Examples / BET-06 | Low — purely a placement decision; both work. The service already has the validated market object at line 88. |
| A5 | Price-history + activity endpoints should also allow RESOLVED (not just the detail read) | Pitfall 3 | Low — surfacing the pre-resolution chart on a resolved market is a nice-to-have; if out of scope, only `get_market_public` needs the RESOLVED allowance. |

**If the planner accepts A1–A5 as written, no user round-trip is needed except possibly A1 (the TenantConfig-vs-columns wording).** A1 is worth a one-line confirmation because it contradicts the literal requirement text.

## Open Questions

1. **BET-06 storage: `markets` columns vs TenantConfig (A1)?**
   - What we know: REQUIREMENTS/ROADMAP say "per market via TenantConfig"; `TenantConfig` is a single-row GLOBAL table (`branding/models.py`, `UNIQUE(tenant_id)`); the global default already lives in `config.py` (`BET_MIN/MAX_STAKE`).
   - What's unclear: whether "via TenantConfig" was loose wording for "operator-configurable" or a literal table choice.
   - Recommendation: per-market columns on `markets` (A1). Confirm with Pol in one line; everything else proceeds regardless.

2. **Backfill historical resolved markets, or re-seed demo data (A3)?**
   - What we know: pre-Phase-12 winners are in `audit_log.payload.winning_outcome` only.
   - What's unclear: whether the demo runs on a fresh DB (no backfill needed) or an existing one.
   - Recommendation: add an idempotent backfill UPDATE to `0010.upgrade()`; it's cheap insurance. Planner decides.

3. **Resolver attribution storage shape (A2/Pitfall 6).**
   - Recommendation: store `resolution_source` token + (house only) the resolving admin's `display_name` snapshot, OR resolve display in the frontend from the token. Small choice; flagged.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 + uv venv | Backend tests/migration | ✓ (per CLAUDE.md env) | 3.12/3.13 | — (use `.venv/Scripts/python.exe`; bare `python` is broken on this host) |
| Docker + testcontainers | Backend integration tests | ✓ (CI) / host-conditional | — | Integration tests are CI-graded; locally gated by host port conflicts with crypto-casino containers (per user memory) |
| Postgres 16 | Migration + integration tests | ✓ (compose/testcontainers) | 16 | — |
| pnpm + Node | Frontend build/tests | ✓ | pnpm 9.15 / Node 20 | — |
| GitHub MCP / `gh` | PR creation | ✓ (PAT env var) | — | — |

**Missing dependencies with no fallback:** none — this phase needs only the existing stack.
**Missing dependencies with fallback:** local backend integration tests may not true-green on this Windows host (Redis/Postgres/port conflicts, per the xpredict test-baseline memory); scan the phase commit range and rely on CI for the integration tier — do NOT treat the ~4 known pre-existing Windows failures as regressions.

## Validation Architecture

> `workflow.nyquist_validation: true` (verified in `.planning/config.json`) — this section is REQUIRED.

### Test Framework
| Property | Value |
|----------|-------|
| Backend framework | pytest + pytest-asyncio (`asyncio_mode="auto"`) + httpx ASGITransport + testcontainers Postgres |
| Backend config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` (testpaths=`tests`, markers `integration`/`unit`) |
| Frontend framework | Vitest (`environmentMatchGlobs`: `.test.tsx`→jsdom, `.test.ts`→node) + `@vitejs/plugin-react` |
| Frontend config file | `frontend/vitest.config.ts` (+ `vitest.setup.ts`) |
| Backend quick run | `cd backend && uv run pytest tests/settlement tests/markets tests/bets -x` (or `.venv/Scripts/python.exe -m pytest ...`) |
| Backend full suite | `cd backend && uv run pytest` |
| Frontend quick run | `cd frontend && pnpm test -- src/lib/__tests__/admin-markets-api.test.ts` |
| Frontend full suite | `cd frontend && pnpm test` (`vitest run`) + `pnpm typecheck` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STL-06 | `mark_resolved` persists winner+source+justification; re-resolve still idempotent | integration | `uv run pytest tests/settlement/test_resolve_market.py -x` | ✅ exists — EXTEND with persist assertions |
| STL-06 | `get_market_public` returns 200 for RESOLVED + `MarketRead` carries resolution fields | integration | `uv run pytest tests/markets/test_public_router.py -x` | ✅ exists — ADD a RESOLVED-returns-200 case |
| STL-06 | Detail page renders the resolution panel on RESOLVED | unit (jsdom) | `pnpm test -- src/components/market-resolution-panel.test.tsx` | ❌ Wave 0 (new component test) |
| ADM-01..04 | CRUD list/create/edit/close through the router | integration | `uv run pytest tests/markets/test_admin_router.py -x` | ✅ exists — backend already covered |
| ADM-01..06 | New admin-markets-api targets the CORRECT prefixes (CRUD `/api/v1`, settlement bare) | unit (node) | `pnpm test -- src/lib/__tests__/admin-markets-api.test.ts` | ❌ Wave 0 (clone `admin-api.test.ts` — the prefix guard) |
| ADM-07 | PATCH criteria → 423 with bets; UI disables the field | integration + unit | `uv run pytest tests/markets/test_admin_router.py::test_update_criteria_locked_with_bets -x` | ✅ exists (backend); add a form-disable unit test |
| STL-02/07, ADM-06 | resolve/reverse/force-settle endpoints settle/reverse correctly | integration | `uv run pytest tests/settlement/test_settlement_router.py tests/settlement/test_force_settle.py -x` | ✅ exists — backend covered |
| STL-02/06/07 | Confirm dialogs validate mandatory justification before submit | unit (jsdom) | `pnpm test -- src/components/admin/resolve-market-dialog.test.tsx` | ❌ Wave 0 (clone the ban-dialog test approach) |
| BET-06 | Per-market min/max enforced server-side (and global fallback when NULL) | integration | `uv run pytest tests/bets/test_bet_router.py -x` | ✅ exists — EXTEND with per-market cases |
| BET-06 | Order form rejects below/above per-market range client-side | unit (jsdom) | `pnpm test -- src/components/order-entry-form.test.tsx` | ✅ exists — EXTEND |

### Sampling Rate
- **Per task commit:** the matching quick run above (e.g. `uv run pytest tests/settlement -x` for an STL-06 task; `pnpm test -- <file>` for a frontend task) + `pnpm typecheck` on any frontend edit.
- **Per wave merge:** `cd backend && uv run pytest` (full) + `cd frontend && pnpm test && pnpm typecheck`.
- **Phase gate:** full backend suite green (CI-graded for the integration tier) + full frontend suite + typecheck green before `/gsd-verify-work`. Scan the phase commit range `origin/main..HEAD`, not absolute counts — ~4 pre-existing Windows-only failures (3 WS-need-Redis + 1 gitleaks full-history) and the orphan `middleware.test.ts` are NOT regressions (per user memory).

### Wave 0 Gaps
- [ ] `frontend/src/lib/__tests__/admin-markets-api.test.ts` — URL-prefix contract guard (clone `admin-api.test.ts`); the single most important new test (Pitfall 1).
- [ ] `frontend/src/components/admin/resolve-market-dialog.test.tsx` (+ reverse/force-settle) — mandatory-justification validation (clone the ban-dialog test).
- [ ] `frontend/src/components/market-resolution-panel.test.tsx` — STL-06 display branch.
- [ ] Extend `backend/tests/settlement/test_resolve_market.py` + `test_settlement_router.py` fakes to the NEW `mark_resolved` signature (these will FAIL to compile until updated — that is the lockstep signal).
- [ ] Extend `backend/tests/markets/test_public_router.py` (RESOLVED→200) and `backend/tests/bets/test_bet_router.py` (per-market limits).
- [ ] No framework install needed — pytest + vitest are present.

## Security Domain

> `security_enforcement` is not present in `.planning/config.json` (absent = enabled). This phase touches admin-gated mutations + a public read, so the relevant ASVS categories are access control and input validation.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Admin Bearer (`current_active_admin`, `is_admin`); player cookie (`current_active_player`). Reused, not re-implemented. |
| V3 Session Management | yes | `admin_jwt` HttpOnly cookie read server-side only (`"use server"` Bearer-forward); token never in client JS. Player `xpredict_session` cookie forwarded server-side for the payout read. |
| V4 Access Control | yes | Every new admin route call goes through `current_active_admin` (401 missing Bearer, 403 non-admin) — verified pattern in `test_admin_router.py` (401/403 cases) and `test_settlement_router.py`. The resolution display shows ONLY the logged-in player's own settled position (their own cookie-gated portfolio), never another user's. |
| V5 Input Validation | yes | Backend is authoritative: `MarketCreate`/`MarketUpdate` (`Field` constraints), `ResolveMarketRequest`/`ReverseSettlementRequest`/`ForceSettleRequest` (`extra="forbid"`, `justification` `min_length=1`). Frontend zod is UX-only mirror. New stake-limit columns validate range server-side. |
| V6 Cryptography | no | No new crypto; reuses Phase 2 HS256 admin JWT. |

### Known Threat Patterns for {Next.js admin UI + FastAPI admin endpoints}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Admin Bearer leaking to client JS | Information Disclosure | `"use server"` module reads HttpOnly cookie server-side; only the JSON result crosses to the client (established `admin-api.ts` pattern) |
| Calling settlement endpoints with the wrong prefix → silent 404 masking an auth bug | Tampering / Repudiation | URL-contract unit test (Pitfall 1) + the real `current_active_admin` gate (401/403 tested) |
| Non-admin reaching market mutations | Elevation of Privilege | `current_active_admin` on every admin route; negative tests already exist (`test_create_market_non_admin_returns_403`) — mirror for any NEW route (none expected; all reuse mounted routers) |
| Player resolution display leaking another user's payout | Information Disclosure | Payout comes from `/bets/me/portfolio` (self-scoped by the player's own cookie, no `user_id` param) — filter by `market_id` client-side of the SSR fetch, never query another user |
| `<style>`/HTML injection via justification text shown publicly | Tampering | Justification is rendered as React text (auto-escaped); do NOT `dangerouslySetInnerHTML`. The audit/justification is plain text (`Field(min_length=1)`, no HTML contract). |
| Force-settle / reverse without justification | Repudiation | Backend enforces `min_length=1` (tested: `test_resolve_422_when_justification_blank`); the confirm dialog also blocks empty client-side |

## Sources

### Primary (HIGH confidence) — direct source reads
- `backend/app/markets/{models,schemas,router,service,enums}.py` — market domain, `MarketRead`, `get_market_public` 404 (line 164), admin CRUD endpoints, 423 criteria-lock (service.py 131-138)
- `backend/app/settlement/{service,adapters,router,market_port,schemas,constants}.py` — `resolve_market`/`reverse_settlement`, `mark_resolved` winner-discard (adapters 31-38), resolve/reverse/force-settle endpoints + `/admin/markets` prefix (router 46), request schemas (`min_length=1`), re-resolve-after-reverse landmine (constants 66-71)
- `backend/app/bets/{router,service,schemas,models,constants}.py` — global stake check (router 92-97), `place_bet` (no per-market limit), `PlaceBetRequest`, portfolio settled positions
- `backend/app/core/config.py` — `BET_MIN_STAKE`/`BET_MAX_STAKE`/`SIGNUP_BONUS_AMOUNT` global constants (lines 79-81)
- `backend/app/branding/{models,schemas}.py` — `TenantConfig` single-row table + `UNIQUE(tenant_id)` (the BET-06 storage evidence)
- `backend/app/auth/{deps,models}.py` — `current_active_admin`/`current_active_player`, `User.display_name`
- `backend/app/main.py` — router mounting + DIFFERENT prefixes (lines 195, 201)
- `backend/alembic/versions/{0003,0007,0009}_*.py` + revision/down_revision sweep — confirmed single head `0009_phase10_tenant_config`; `0007` is the `add_column` template; next is `0010`
- `backend/tests/settlement/test_settlement_router.py`, `tests/markets/{conftest,test_admin_router}.py` — exact integration patterns + the `FakeMarketResolver.mark_resolved` signature that must change
- `frontend/src/lib/{admin-api,branding-admin-api,api}.ts` + `__tests__/admin-api.test.ts` — Bearer-forward pattern + the prefix-contract regression guard
- `frontend/src/components/admin/{admin-nav,users-data-table,branding-form,ban-confirm-dialog,kpi-card,kpi-dashboard}.tsx` — clone targets (nav placeholder lines 56-57; table; form; confirm dialog; pending-resolutions card lines 172-175)
- `frontend/src/app/admin/{users/page,branding/page,layout}.tsx`, `frontend/src/app/markets/[slug]/page.tsx`, `frontend/src/app/portfolio/page.tsx` — page clone targets + STL-06 render target + payout source
- `.planning/v1.0-MILESTONE-AUDIT.md`, `ROADMAP.md` (Phase 12 + Phases 4/5/7), `REQUIREMENTS.md`, `.planning/config.json` — design source, success criteria, requirement text, nyquist flag
- `Skill("spike-findings-xpredict")` + `references/settlement.md` — settlement invariants (idempotency via PENDING filter + `settled_at`/`resolved_at`; losers fund winners; never double-debit; ACID)

### Secondary (MEDIUM confidence)
- User auto-memory: xpredict test baseline (~4 pre-existing Windows failures, not regressions), xpredict GSD env (CWD=xpredict), Windows worktree/git path quirks — used to scope verification realistically.

### Tertiary (LOW confidence)
- None. Every claim in this document is grounded in a file read this session.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new deps; every library verified in the repo manifests/source.
- Architecture / endpoint contracts: HIGH — every endpoint, schema, and prefix read directly from source; the two-prefix landmine is corroborated by an existing regression test.
- STL-06 backend change: HIGH — the exact discard point (`mark_resolved`), the 404 guard, and the missing `MarketRead` fields are all confirmed in source.
- BET-06 storage recommendation (columns vs TenantConfig): MEDIUM — recommendation is evidence-based (TenantConfig is single-row), but contradicts the literal requirement wording; flagged as A1 for a one-line confirmation.
- Pitfalls: HIGH — drawn from in-repo comments (`constants.py` re-resolve note), existing tests, and the audit.

**Research date:** 2026-06-03
**Valid until:** 2026-07-03 (stable — the codebase is the source of truth; re-verify only if Phases 4/5/7 files change before planning)
