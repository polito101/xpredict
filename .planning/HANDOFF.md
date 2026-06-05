# HANDOFF — live operational state

> **Updated:** 2026-06-06 (Phase 17 closeout — PR opened + CI 7/7 green) · **Milestone:** v1.2 Credible Catalog · **Phase 17 of 18 — DONE: PR [#31](https://github.com/polito101/xpredict/pull/31) OPEN, CI 7/7 GREEN, MERGEABLE, 0 drift → MERGE READY, awaiting Pol's review/merge**
> Read this first. STATE.md + ROADMAP.md are the formal GSD truth; this is the live "what's happening NOW + what NOT to touch."
> Verify live state from git (`git log`, `origin/main`, `gh pr ...`), not these docs alone — they can drift.

---

## TL;DR

**Phase 17 (Catalog Browse UI, Event Detail & Admin Event Ops) is COMPLETE: the first FRONTEND phase of v1.2, built entirely against the merged Phase-16 API (zero backend changes).** Executed end-to-end autonomously (5 plans, ~30 frontend files), reviewed by 2 independent reviewers (framing LOCK / security / a11y / BRW-06 = PASS; 1 HIGH + 2 MED + 4 LOW all fixed), verified goal-backward (PASSED). Shipped to **PR [#31](https://github.com/polito101/xpredict/pull/31)**: OPEN, **all 7 CI checks GREEN**, `mergeable=MERGEABLE` with **0 drift** vs `origin/main`. Only remaining action: **Pol's review/merge** (`reviewDecision=REVIEW_REQUIRED`; `main` is protected). **Status: MERGE READY.**

Phase 16 (PR #30) is **MERGED** into `origin/main` (`df137f9`), along with Phases 13 (#25), 14 (#28), 15 (#29) — all v1.2 backend phases are on main.

---

## Phase 17 — exact status

- **Branch / PR:** `gsd/phase-17-catalog-browse-ui-event-detail-admin-event-ops` (forked off `origin/main` @ `df137f9`; **0 behind, 11 ahead**, no drift). **PR [#31](https://github.com/polito101/xpredict/pull/31) OPEN**, `mergeable=MERGEABLE`, `mergeStateStatus=BLOCKED` ONLY by `reviewDecision=REVIEW_REQUIRED`, Pol requested as reviewer. Opened via `gh` (the worktree session lacks the `create_pull_request` MCP — the documented GOTCHA; only Pol merges).
- **Delivers (EVT-02..05, BRW-06; the UI for the Phase-16 contract):**
  - **Catalog browse (`/`)** — the homepage upgraded from the plain `/markets` list to the curated `/catalog`: debounced search + category chips (empty never render) + status/sort + explicit empty states. Files: `lib/catalog.ts`, `components/catalog/{event-card,catalog-controls}.tsx`, `app/page.tsx`, `app/loading.tsx` (retired the orphaned `market-list.tsx`).
  - **Event detail (`/events/[slug]`)** — independent per-outcome rows (the **framing LOCK**: own YES odds, never sum-to-100), bet-on-one-outcome reusing `OrderEntryForm` against the constituent child (real YES+NO via `fetchMarket(child_slug)`), per-child `PriceHistorySection`, single live socket (cap). Files: `components/event/{event-detail-view,outcome-row,event-status-badge}.tsx`, `app/events/[slug]/{page,error}.tsx`.
  - **Admin event ops (`/admin/events*`)** — create/edit form (`useFieldArray` outcomes, min 2, 423 edit-lock) + resolve/void/reverse dialogs (server two-step preview→execute + mandatory justification). Files: `lib/admin-events-{types,api}.ts`, `components/admin/{event-form,event-detail-admin-actions,resolve-event-dialog,void-event-dialog,reverse-event-dialog}.tsx`, `app/admin/events/{page,new/page,[slug]/page}.tsx`, `admin-nav.tsx` (+Events link).
- **Tests:** 36 new (catalog 6 + admin-events 9 + event-card 5 + catalog-controls 5 + event-detail-view 4 + event-form 4 + void-dialog 2 + resolve-dialog 1) → **188/188 vitest green**; Linux CI `frontend` job GREEN (typecheck + lint + test + build, 1m19s).
- **Code review** (`17-REVIEW.md`, status `clean`): framing LOCK / security / a11y / BRW-06 = PASS. H1 (category-clear), M2 (metadata edit churned children), M1 (select() race), L1–L4 — **all fixed**; M1 has a regression test.
- **Verification** (`17-VERIFICATION.md`): status `passed`, all 4 success criteria + EVT-02..05/BRW-06 traced to code + proof. **UI review** (`17-UI-REVIEW.md`): 6/6 PASS (advisory).

## Post-PR audit — DONE (the "PR opened ≠ done" gate)

- **Drift:** 0 behind `origin/main` (`df137f9`), 11 ahead. No conflicts. ✓
- **CI: 7/7 GREEN** — `frontend` ✓ (1m19s), `dry-run` ✓, `gitleaks (full history)` ✓, `bandit` ✓, `pip-audit` ✓, `pnpm-audit` ✓, `zap-baseline` ✓. ✓
- **Mergeability:** `MERGEABLE`, `BLOCKED` only by the required review (Pol). ✓
- **Invariants:** frontend-only — zero backend changes, zero new dependencies; consumes the merged Phase-16 endpoints verbatim. ✓

## Environment notes (Windows worktree)

- **Frontend local validation works** with the pinned `corepack pnpm@9.15.0` (`tsc`/`eslint`/`vitest` + `next build --webpack`). Default Turbopack `next build` flakes on the worktree (pnpm symlink + Sentry) → use the webpack builder locally; **trust Linux CI `frontend`** as authoritative. Install via `pnpm install --frozen-lockfile` (non-destructive; never unpinned `corepack pnpm` → 11.x).
- Execution ran INLINE (spawned `gsd-executor` agents stream-idle-timeout on this worktree; read-only review/discovery agents are fine).

## What NOT to touch

- Don't re-open / re-verify Phase 17 — engineering-complete; the only open action is Pol's merge of PR #31.
- Don't push to `main` or self-merge — PR-only; **only Pol merges**.
- Don't modify the Phase-16 backend (catalog/event routers/services) — Phase 17 consumes it byte-for-byte unchanged.
- Per-outcome framing: NEVER introduce a stacked/normalized/sum-to-100 outcome bar — it would visibly lie (the gating invariant).

## Recommended next session — Phase 18 (after #31 merges)

- **Phase 18 = Seed/Demo Harness for Multi-outcome + Categories** — reqs DEMO-01..04 (BACKEND/seed phase). Extend `bin/seed_demo.py`: ≥1 multi-outcome event per category (3–8 outcomes, plausible prices, non-flat history), open + partially-resolved + resolved + void states, filled tabs, pinned featured allow-list; idempotent `demo-reset` with a green double-entry integrity check. **The milestone's end-to-end integration acceptance test** (exercises model → sync → settlement → API → UI).
- **Prereq:** start ONLY after Pol merges PR #31, from a fresh `origin/main` checkout. New session, repo-rooted.
- **Kickoff:** `/gsd-autonomous phase 18` (single-phase, 1 PR — the same flow used for 13/14/15/16/17).
- After Phase 18: v1.2 milestone complete → audit/complete/cleanup.

## Standing deferred items (carried from v1.0/v1.1, unchanged)

| Category | Item | Status |
|----------|------|--------|
| legal (gating) | Spanish counsel review of ToS + token policy | Open — **not deferrable** before any live operator demo |
| human-UAT | Phase 12 `12-HUMAN-UAT.md` | 3 scenarios open |
| verification | Phases 03 / 04 / 05 | 3 VERIFICATION.md missing (backends shipped) |
| backend (Phase 17 follow-up) | Dedicated admin event-list endpoint + editable `resolution_criteria` on `UpdateEventRequest` | Deferred — Phase 17 UI uses the public catalog (house-filtered) for the admin list; criteria not editable post-create |
