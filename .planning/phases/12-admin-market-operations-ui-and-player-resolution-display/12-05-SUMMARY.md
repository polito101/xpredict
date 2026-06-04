---
phase: 12-admin-market-operations-ui-and-player-resolution-display
plan: 05
subsystem: ui
tags: [nextjs, server-components, tanstack, react-hook-form, zod, shadcn, vitest, typescript]

# Dependency graph
requires:
  - phase: 12-admin-market-operations-ui-and-player-resolution-display (Plan 12-02)
    provides: "admin-markets-api.ts (fetchMarkets/createMarket/updateMarket) + admin-markets-types.ts (MarketListItem/MarketCreateBody/MarketUpdateBody/PaginatedResponse/MarketListParams/MarketStatus/MarketSource) + MarketStatusBadge — imported, not re-created"
  - phase: 08-admin-crm (Plan 08-03)
    provides: "users-data-table.tsx + admin/users/page.tsx + admin-format.ts + admin-query.ts + admin-nav.tsx — the table/page/nav clone sources"
  - phase: 10-branding (Plan 10-03)
    provides: "branding-form.tsx — the RHF+zod+422-mapping form clone source"
provides:
  - "admin-nav 'Markets' link enabled (real /admin/markets Link, active-highlight inherited) — replaces the disabled placeholder span"
  - "markets-data-table.tsx: server-driven TanStack v8 list with source/status/category filters, MarketStatusBadge + SourceBadge columns, rows-as-links to /admin/markets/{id}, skeleton/empty/error states"
  - "app/admin/markets/page.tsx: force-dynamic Server Component shell + 'Create market' button"
  - "market-form.tsx: shared RHF+zod create/edit form (BET-06 stake fields, ADM-07 criteria lock, 422 field mapping) + parseMarketApiError helper — CONSUMED by the 12-06 [id] detail/edit host"
  - "app/admin/markets/new/page.tsx: create route rendering MarketForm mode=create"
affects: [12-06, market detail page, resolve-market-dialog, reverse-settlement-dialog, force-settle-dialog]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shared create/edit form via a `mode` discriminant: a single MarketForm covers both flows; the odds field name is mapped at submit (initial_odds_yes for create, odds_yes for edit) so the form never sends the wrong wire key"
    - "Form-level error decode helper (parseMarketApiError) mirroring parseBrandingApiError: recovers {status, fieldErrors} from a JSON message, falling back to the legacy 'API error: <status>' string"
    - "Three-filter TanStack clone: the single-Select filter bar from users-data-table extended to source + status + category, dropping search/date/CSV-export (none specified for markets)"

key-files:
  created:
    - frontend/src/components/admin/markets-data-table.tsx
    - frontend/src/app/admin/markets/page.tsx
    - frontend/src/components/admin/market-form.tsx
    - frontend/src/components/admin/__tests__/market-form.test.tsx
    - frontend/src/app/admin/markets/new/page.tsx
  modified:
    - frontend/src/components/admin/admin-nav.tsx

key-decisions:
  - "MarketForm uses a single FORM-level odds field `odds_yes` for both modes; the create/edit wire-name split (initial_odds_yes vs odds_yes) is applied only at submit-time body construction — keeps the form schema unified while honoring the verified backend discrepancy."
  - "The min<=max cross-field rule lives on the zod schema's `.refine` with `path:['max_stake']` so the error renders under the Max stake field; Number() is used only for the comparison, money stays a string (SP-1 / threat T-12-16)."
  - "Optional fields (category/min_stake/max_stake) are OMITTED from the body when blank rather than sent as empty strings — the backend treats omission as 'use the default', matching the BET-06 'blank = platform default' contract."
  - "In edit-mode with bets, resolution_criteria is both DISABLED in the UI and OMITTED from the PATCH body (defense in depth over the backend's authoritative 423 CRITERIA_LOCKED)."
  - "Category filter is a free-text Input (not a Select) — the backend filter is a free-form string Query param and there is no fixed category enumeration."

patterns-established:
  - "Pattern 1: a shared admin CRUD form keyed by a `mode: 'create' | 'edit'` prop with `initialValues`/`marketId`/`betCount` — the 12-06 detail page hosts the same component in edit-mode."
  - "Pattern 2: form API-error decode helper colocated with the form (parseMarketApiError) so the 422 field-error mapping survives the 'use server' async-only export constraint."

requirements-completed: [ADM-01, ADM-02, ADM-03, ADM-07, BET-06]

# Metrics
duration: 5min
completed: 2026-06-03
---

# Phase 12 Plan 05: Admin Market-Management Surface Summary

**Enabled the admin Markets nav + the `/admin/markets` server-driven TanStack list (source/status/category filters) + the shared create/edit `market-form` (BET-06 stake fields, ADM-07 criteria lock, 422 field mapping), all verbatim clones of shipped Phase 8/10 admin files wired to the 12-02 `admin_market_router` API layer — closing BLOCKER-3.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-06-03T14:58:13Z
- **Completed:** 2026-06-03T15:03:18Z
- **Tasks:** 2 (Task 2 is TDD: RED → GREEN)
- **Files modified:** 6 (5 created, 1 edited)

## Accomplishments
- **The Markets surface is now reachable through the product.** The `admin-nav.tsx` disabled `<span>Markets</span>` placeholder is gone, replaced by a real `/admin/markets` `LINKS` entry (active-highlight + `aria-current` inherited automatically). ADM-01..04/07 are no longer raw-API-only.
- **`/admin/markets` is a full server-driven list** — a verbatim clone of `users-data-table.tsx` with the firstRender-skip fetch effect, `resetToFirstPage` on every filter change, rows-as-links a11y, and skeleton/empty/error states preserved. The single status Select became THREE filters (source / status / category); search/date-range/CSV-export were dropped (none specified for markets). Empty copy is the spec's "No markets found".
- **`market-form.tsx` is one shared component for both create and edit** — RHF+zod mirroring `MarketCreate`/`MarketUpdate`, BET-06 optional Min/Max stake string fields with a `min<=max` cross-field rule, the ADM-07 criteria lock (disabled + locked helper when `betCount>0`), a `Loader2` spinner, sonner toasts, and a 422 → inline `FormMessage` field-error map. Built TDD (RED → GREEN, 4/4).
- The create route `/admin/markets/new` renders the form in create-mode; the page shell degrades to an empty table on a failed initial load.

## Task Commits

Each task was committed atomically:

1. **Task 1: Enable Markets nav + markets-data-table + /admin/markets list page** — `1577236` (feat)
2. **Task 2: market-form (create/edit, BET-06, ADM-07) + create route + test (TDD)** — `edbd150` (test/RED) → `c37d85b` (feat/GREEN)

**Plan metadata:** see final docs commit.

_REFACTOR phase skipped — the clones were idiomatic on first write; no cleanup commit needed._

## Files Created/Modified
- `frontend/src/components/admin/admin-nav.tsx` (modified) — Added `{ href: "/admin/markets", label: "Markets" }` to `LINKS` (between Users and Audit log); removed the disabled placeholder span; updated the header comment.
- `frontend/src/components/admin/markets-data-table.tsx` (created) — Server-driven TanStack v8 list; columns question / source / status / category / deadline / bet_count / created_at / View; source+status+category filter bar; `fetchMarkets`; default sort `created_at desc`; `PAGE_SIZE=20`.
- `frontend/src/app/admin/markets/page.tsx` (created) — `force-dynamic` Server Component; initial `fetchMarkets` with degrade-to-empty; H1 "Markets" + top-right "Create market" Button → `/admin/markets/new`.
- `frontend/src/components/admin/market-form.tsx` (created) — Shared create/edit RHF+zod form; BET-06 stake fields; ADM-07 lock; `parseMarketApiError`; create→`initial_odds_yes`, edit→`odds_yes`; toasts + 422 mapping.
- `frontend/src/components/admin/__tests__/market-form.test.tsx` (created) — 4 jsdom tests: required-field errors, `min>max`, ADM-07 disabled+helper, 422 field mapping.
- `frontend/src/app/admin/markets/new/page.tsx` (created) — Create route rendering `<MarketForm mode="create" />` in the admin shell.

## Decisions Made
- **Single form-level odds field, wire-name split at submit.** `MarketFormValues.odds_yes` covers both modes; the body builder sends `initial_odds_yes` for create and `odds_yes` for edit — the form schema stays unified while honoring the verified backend discrepancy (12-02 encoded it in the two body types).
- **Blank optional fields are omitted, not sent empty.** category/min_stake/max_stake omitted from the body when blank → backend "use the default", matching BET-06's "blank = platform default".
- **Edit-mode criteria lock is defense-in-depth.** When `betCount>0`, resolution_criteria is BOTH disabled in the UI AND omitted from the PATCH body; the backend's 423 CRITERIA_LOCKED remains authoritative.
- **Category filter is a free-text Input.** The backend filter is a free-form string Query param with no fixed enumeration, so a Select would be wrong.
- **`parseMarketApiError` handles both the JSON and legacy message shapes.** `admin-markets-api.ts` throws `Error("API error: <status>")` (legacy), so the helper extracts the status from that string while still recovering structured `{status, fieldErrors}` from a richer JSON message — mirroring `parseBrandingApiError`.

## Deviations from Plan

None - plan executed exactly as written.

The plan's only adaptation latitude (the create/edit odds field-name split and the money-as-string discipline) was pre-specified in the `<action>`/`<behavior>` blocks and in the 12-02 body types; I implemented exactly that. No Rule 1-4 deviations were needed: typecheck and the scoped tests were green on first GREEN pass, no blocking issues, no missing critical functionality, no architectural changes. The pre-existing DEF-FE-01 orphan `middleware.test.ts` did not surface during scoped typecheck/test, so no `deferred-items.md` entry was needed.

## Issues Encountered
None. The clone sources (`users-data-table.tsx`, `admin/users/page.tsx`, `branding-form.tsx`) transferred cleanly; the 12-02 API/types/badge imported with zero collision. The `branding-form.test.tsx` mock harness (mock the `"use server"` helper + sonner) was the direct template for the market-form test, plus a `useRouter` mock for the create-mode submit navigation.

## Known Stubs
None. Every surface is wired to a real 12-02 endpoint wrapper:
- The list calls `fetchMarkets` (live `GET /api/v1/admin/markets`).
- The form calls `createMarket` / `updateMarket` (live `POST` / `PATCH`).
- Rows link to `/admin/markets/{id}` and the header "Create market" links to `/admin/markets/new`. The `/admin/markets/{id}` DETAIL/EDIT host page is NOT in this plan's scope — it lands in **12-06** (which also adds ADM-04 close + the resolve/reverse/force-settle dialogs). The `market-form` is intentionally shared and ready for 12-06 to render in edit-mode. This is a documented cross-plan boundary, not an unwired stub.

## Threat Flags

None. This plan adds no new network endpoint, auth path, or schema change — it is a client-only surface funneling every call through the 12-02 `"use server"` Bearer-forward layer (admin_jwt stays HttpOnly server-side, T-12-17). The threat register's `mitigate` items are honored: criteria-lock + 422 mapping are UX mirrors over the authoritative backend (T-12-15); money stays a string with `Number()` only for the compare (T-12-16); zero package installs (T-12-SC).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- **12-06 ready.** The shared `MarketForm` (edit-mode + `betCount` + `initialValues`/`marketId` props), `MarketsDataTable`, and the enabled nav are in place. 12-06 builds the `/admin/markets/[id]` detail/edit host (rendering `<MarketForm mode="edit" ... />`), the ADM-04 close action, and the resolve/reverse/force-settle dialogs (consuming the 12-02 settlement wrappers + the existing `closeMarket`).
- **Load-bearing fact for 12-06:** the create/edit odds wire-name split is already handled inside `MarketForm` — the detail page just passes `mode="edit"`, `initialValues`, `marketId`, and `betCount`; it must NOT rebuild the body.
- No blockers.

## Self-Check: PASSED

All 6 created/modified files verified on disk; all 3 task commits (`1577236`, `edbd150`, `c37d85b`) verified in git log. Final verification: `pnpm typecheck` exit 0; `market-form.test.tsx` 4/4 + `market-status-badge.test.tsx` 15/15 (19/19 green); no `pnpm-lock.yaml`/`pnpm-workspace.yaml` churn.

---
*Phase: 12-admin-market-operations-ui-and-player-resolution-display*
*Completed: 2026-06-03*
