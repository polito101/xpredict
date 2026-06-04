---
phase: 12-admin-market-operations-ui-and-player-resolution-display
plan: 06
subsystem: ui
tags: [react, nextjs, admin, settlement, dialogs, shadcn, radix]

# Dependency graph
requires:
  - phase: 12-01
    provides: winner persisted on the markets row inside the settlement ACID tx; resolution_source token; RESOLVED markets return 200
  - phase: 12-02
    provides: admin-markets-api 'use server' wrappers (resolveMarket/reverseSettlement/forceSettle on the BARE prefix, closeMarket on /api/v1) + MarketStatusBadge
  - phase: 12-04
    provides: MarketResolutionPanel + the player resolution display (STL-06) in markets/[slug]
  - phase: 12-05
    provides: shared MarketForm (mode="create"|"edit") with the criteria-locks-when-bet_count>0 behavior
provides:
  - "Four two-step settlement/close action dialogs (resolve / reverse / force-settle / close) wired to the 12-02 wrappers with mandatory client-side justification and stay-open-during-submit"
  - "/admin/markets/[id] detail page hosting the 12-05 edit form + status/source-gated action buttons (the last seam that makes the operator->player resolution loop reachable through the product)"
  - "KPI 'Pending resolutions' card deep-link to /admin/markets?status=CLOSED"
  - "SC#5 end-to-end-through-the-UI acceptance: operator->player resolution loop passes with no raw-API step (human-verify gate APPROVED)"
affects: [phase-12-verification, phase-12-code-review, v1.0-milestone-re-audit]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-step confirm + mandatory-justification dialog cloned verbatim from ban-confirm-dialog.tsx (reset-on-open effect, onOpenChange close-guard while submitting, role=alert validation error, destructive Confirm + Loader2)"
    - "Server Component detail page fetches the entity, hands it to a 'use client' island that hosts the action buttons + dialogs (mirrors admin/users/[id] convention)"
    - "Status + source gating computed in the client island: OPEN/CLOSED+HOUSE -> Resolve; OPEN/CLOSED+POLYMARKET -> Force-settle; RESOLVED -> Reverse; OPEN -> Close"

key-files:
  created:
    - frontend/src/components/admin/resolve-market-dialog.tsx
    - frontend/src/components/admin/reverse-settlement-dialog.tsx
    - frontend/src/components/admin/force-settle-dialog.tsx
    - frontend/src/components/admin/close-market-dialog.tsx
    - frontend/src/components/admin/settlement-dialog-utils.ts
    - frontend/src/components/admin/__tests__/settlement-dialogs.test.tsx
    - frontend/src/app/admin/markets/[id]/page.tsx
    - frontend/src/components/admin/market-detail-actions.tsx
  modified:
    - frontend/src/components/admin/kpi-card.tsx

key-decisions:
  - "Settlement dialogs call ONLY the 12-02 wrappers, never a hand-built URL — preserves the BARE /admin/markets/{id}/... settlement-prefix contract (T-12-19) so a wrong-prefix call cannot silently 404"
  - "The detail page action buttons live in a sibling 'use client' island (market-detail-actions.tsx) rather than inline in the Server Component, mirroring the shipped admin/users/[id] hosts-actions convention; the Server Component stays a thin fetch + not-found degrade shell"
  - "Reverse dialog body uses the UI-SPEC Reverse copy guard verbatim and explicitly does NOT promise clean re-resolution (Pitfall 5 / T-12-21) — the v1 idempotency-key-collision limitation is surfaced, not silently invited"
  - "close-market-dialog has NO reason field (the API takes none) and resolve/force-settle gain a YES/NO outcome Select above the mandatory justification"
  - "Shared per-action copy + the 401/403 -> 'Your session expired. Please sign in again.' status-branching helper extracted to settlement-dialog-utils.ts so all four dialogs map the wrapper's thrown status identically"

patterns-established:
  - "Two-step settlement/close dialog: clone ban-confirm-dialog, swap the wrapper call + copy, keep the close-guard and reset-on-open invariants"
  - "Detail-page-hosts-gated-actions: Server Component fetch -> client island computes status/source gating -> dialog success calls router.refresh()"

requirements-completed: [STL-02, STL-07, ADM-05, ADM-06, ADM-04]

# Metrics
duration: ~20min
completed: 2026-06-03
---

# Phase 12 Plan 06: Admin Settlement Actions + Market Detail Host Summary

**Four two-step resolve/reverse/force-settle/close dialogs (clones of ban-confirm-dialog, mandatory justification, reverse copy-guard) wired through the 12-02 BARE-prefix wrappers, hosted on a new /admin/markets/[id] detail page that embeds the 12-05 edit form behind status/source gating, plus a KPI Pending-resolutions deep-link — closing the operator->player resolution loop end-to-end through the UI (SC#5 APPROVED).**

## Performance

- **Duration:** ~20 min (implementation 17:11→17:31, then the SC#5 human-verify gate)
- **Started:** 2026-06-03T17:11:28+02:00 (TDD RED commit)
- **Completed:** 2026-06-03 (SC#5 gate approved by Pol)
- **Tasks:** 3 (Task 1 TDD auto, Task 2 auto, Task 3 human-verify gate — APPROVED)
- **Files modified:** 9 (8 created, 1 modified)

## Accomplishments
- The four operator settlement/close action dialogs (resolve / reverse / force-settle / close), each a verbatim clone of `ban-confirm-dialog.tsx`: reset-on-open effect, `onOpenChange` close-guard while submitting, mandatory-justification `role="alert"` validation, destructive Confirm + `Loader2`, success toast + parent refetch.
- A new `/admin/markets/[id]` detail page: a Server Component that `fetchMarketAdmin(id)` and degrades to a not-found/error state, handing the market to the `market-detail-actions.tsx` `"use client"` island that embeds the 12-05 `MarketForm` (edit mode) and renders the status/source-gated action buttons + dialogs.
- The KPI "Pending resolutions" card wrapped in a `next/link` to `/admin/markets?status=CLOSED` (A-KPI-LINK) with the card visual otherwise unchanged.
- The BARE `/admin/markets/{id}/resolve|reverse|force-settle` settlement-prefix contract honored end-to-end: the dialogs only ever call the 12-02 wrappers (T-12-19), never a hand-built URL.
- SC#5 — the full operator→player resolution loop — verified end-to-end through the product UI (no raw-API step) and **APPROVED** by Pol. This is the closing acceptance for Phase 12.

## Task Commits

Each task was committed atomically:

1. **Task 1 (TDD RED): failing test for settlement dialogs** — `180e66e` (test)
2. **Task 1 (TDD GREEN): resolve/reverse/force-settle/close dialogs + settlement-dialog-utils** — `83ea0ae` (feat) — settlement-dialogs test 12/12 green
3. **Task 2: /admin/markets/[id] detail page (edit + gated actions) + market-detail-actions island + KPI deep-link** — `c2470f9` (feat) — kpi-card test 7/7 green
4. **Task 3: SC#5 end-to-end-through-the-UI acceptance** — human-verify gate, **APPROVED** by Pol (no code; the gate validates the full loop)

**Plan metadata:** docs(12-06) — completes the plan (this SUMMARY + STATE/ROADMAP/REQUIREMENTS)

_Note: Task 1 was executed under the plan's `tdd="true"` flag — RED (`180e66e`) then GREEN (`83ea0ae`); no REFACTOR commit was needed (the clones landed clean against the test)._

## Files Created/Modified
- `frontend/src/components/admin/resolve-market-dialog.tsx` - two-step resolve: YES/NO outcome `<Select>` above a mandatory justification; calls `resolveMarket(id, {winning_outcome_id, justification})`; toast "Market resolved."
- `frontend/src/components/admin/reverse-settlement-dialog.tsx` - justification-only reverse; body uses the Reverse copy guard ("does not re-open the market for a clean re-resolution"); calls `reverseSettlement(id, {justification})`; toast "Settlement reversed."
- `frontend/src/components/admin/force-settle-dialog.tsx` - outcome Select + justification; calls `forceSettle(id, {winning_outcome_id, justification})`; toast "Market force-settled."
- `frontend/src/components/admin/close-market-dialog.tsx` - NO reason field; consequence copy ("This stops the market from accepting new bets..."); calls `closeMarket(id)`; toast "Market closed."
- `frontend/src/components/admin/settlement-dialog-utils.ts` - shared per-action copy + the 401/403 → "Your session expired. Please sign in again." status-branch helper reused by all four dialogs
- `frontend/src/components/admin/__tests__/settlement-dialogs.test.tsx` - jsdom suite: empty-justification block + correct wrapper call per dialog; reverse copy-guard string; close has no reason field (12/12)
- `frontend/src/app/admin/markets/[id]/page.tsx` - Server Component (`force-dynamic`) detail page: `fetchMarketAdmin(id)`, header with question + `MarketStatusBadge` + source, not-found/error degrade, hands the market to the actions island
- `frontend/src/components/admin/market-detail-actions.tsx` - `"use client"` island: embeds `MarketForm mode="edit"` + the status/source-gated Resolve/Force-settle/Reverse/Close buttons + their dialogs; `router.refresh()` on any dialog success
- `frontend/src/components/admin/kpi-card.tsx` - wrapped the "Pending resolutions" KpiCard in `<Link href="/admin/markets?status=CLOSED">`; card markup otherwise unchanged

## Decisions Made
- **Settlement calls go only through the 12-02 wrappers.** The dialogs never construct a settlement URL, so the BARE `/admin/markets/{id}/...` prefix split is impossible to break from the UI (T-12-19 mitigation).
- **Action buttons in a client island, not inline.** `market-detail-actions.tsx` hosts the gating + dialogs; the Server Component stays a thin fetch/degrade shell — mirrors the shipped `admin/users/[id]` hosts-actions convention.
- **Reverse copy guard verbatim (Pitfall 5 / T-12-21).** The reverse dialog body states reversal restores the pre-settlement state for audit/correction and does NOT promise re-resolution; the known v1 idempotency-key-collision limitation is surfaced, not invited.
- **`settlement-dialog-utils.ts` extracted** so the four dialogs share copy + the identical 401/403→session-expired status branch instead of duplicating the catch logic.

## Deviations from Plan

### Auto-fixed Issues

None requiring a code change. One operational deviation worth recording:

**1. [Operational] Interrupted-then-resumed execution after a transient provider overload**
- **Found during:** the autonomous run of Tasks 1–2
- **Issue:** a transient upstream provider overload interrupted the execution mid-plan; the run was resumed from the last committed task rather than restarted.
- **Fix:** resumed from the verified commit state — no task was redone, no scope or behavior changed. All three implementation commits (`180e66e`, `83ea0ae`, `c2470f9`) are intact and were re-verified on resume.
- **Files modified:** none (resume only)
- **Verification:** `git log --oneline --grep="12-06"` shows the three commits in order; created files all present.

---

**Total deviations:** 0 code deviations; 1 operational (interrupt/resume, no scope or behavior change).
**Impact on plan:** None. The plan executed as written; the interruption affected only the execution session, not the output.

## TDD Gate Compliance

Task 1 ran under `tdd="true"`. Gate sequence is present in the git log:
1. **RED:** `180e66e` test(12-06): add failing test for settlement dialogs
2. **GREEN:** `83ea0ae` feat(12-06): implement settlement + close dialogs — settlement-dialogs test 12/12 green
3. **REFACTOR:** not required (clones passed clean; no separate refactor commit)

No test passed unexpectedly during RED (the dialog components did not yet exist).

## Machine Verification
- `settlement-dialogs.test.tsx` — **12/12 green** (empty-justification block + correct wrapper call per dialog; reverse copy-guard string; close has no reason field).
- `kpi-card` test — **7/7 green** (Pending-resolutions card deep-link).
- `pnpm typecheck` — **exit 0** (all 12-06 source type-clean; the only repo-wide typecheck error remains the pre-existing DEF-FE-01 orphan `middleware.test.ts`, out of scope).

## SC#5 Human-Verify Gate — APPROVED

Task 3 was the blocking SC#5 walk-through (operator→player resolution loop, entirely through the UI, no raw-API step): Create (ADM-02) → List+filter (ADM-01) → Bet with min/max guard (BET-06) → Criteria lock (ADM-07) → Resolve (ADM-05/STL-02) → Player resolution display (STL-06) → Reverse (STL-07) → Force-settle (ADM-06) → KPI deep-link. **Pol verified the loop end-to-end and responded "approved."** This is the closing acceptance for the v1.0-closure phase; the audit's Flows 1 & 3 now pass through the product.

## Known Stubs
None. Every dialog is wired to its live 12-02 wrapper; the detail page fetches real market data; the KPI card links to a real filter route. No placeholder/empty-data paths were introduced.

## Issues Encountered
None during planned work (beyond the transient provider-overload interruption noted under Deviations, which was a session interruption, not an implementation problem).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 12 is functionally complete (6/6 plans): the player resolution display (12-04), admin market CRUD (12-05), per-market stake limits (12-03), and the resolve/reverse/force-settle/close operator actions (this plan) are all reachable through the UI over the winner-persisting backend (12-01).
- SC#5 (the cross-slice integration acceptance) passed through the UI — the v1.0-milestone re-audit's UI/integration blockers are addressed.
- Ready for `/gsd-verify-work 12` → `/gsd-code-review` → PR. The v1.0 milestone is not archived until the re-audit passes.

## Self-Check: PASSED

All claimed created files exist on disk:
- `frontend/src/components/admin/resolve-market-dialog.tsx` ✓
- `frontend/src/components/admin/reverse-settlement-dialog.tsx` ✓
- `frontend/src/components/admin/force-settle-dialog.tsx` ✓
- `frontend/src/components/admin/close-market-dialog.tsx` ✓
- `frontend/src/components/admin/settlement-dialog-utils.ts` ✓
- `frontend/src/components/admin/__tests__/settlement-dialogs.test.tsx` ✓
- `frontend/src/app/admin/markets/[id]/page.tsx` ✓
- `frontend/src/components/admin/market-detail-actions.tsx` ✓
- `frontend/src/components/admin/kpi-card.tsx` (modified) ✓

All claimed commit hashes are present in `git log`:
- `180e66e` (test — TDD RED) ✓
- `83ea0ae` (feat — TDD GREEN) ✓
- `c2470f9` (feat — detail page + KPI deep-link) ✓

---
*Phase: 12-admin-market-operations-ui-and-player-resolution-display*
*Completed: 2026-06-03*
