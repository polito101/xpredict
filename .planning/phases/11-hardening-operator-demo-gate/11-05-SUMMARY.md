---
phase: 11-hardening-operator-demo-gate
plan: 05
subsystem: responsive-player-ui
tags: [responsive, mobile, tailwind, css-only, plt-07, sc1, frontend, human-verify, player-ui]
status: in-progress  # Task 1 (auto, responsive CSS) DONE; Task 2 (checkpoint:human-verify, gate=blocking) PENDING — visual QA at 360/390/414/768px

# Dependency graph
requires:
  - phase: 09-user-app-ux-polish-market-detail-real-time
    plan: 04
    provides: "the player market-detail page + order-entry form being made responsive here (the surfaces this CSS pass audits)"
  - phase: 03-wallet-double-entry-ledger
    plan: 05
    provides: "the player /wallet read page (balance + transaction history) made responsive here"
provides:
  - "Responsive (no horizontal scroll, 360-768px) wallet history — px-4 sm:px-6 gutter + transaction rows that shrink the reason (min-w-0/truncate) and keep the amount intact (shrink-0/whitespace-nowrap)"
  - "Responsive portfolio cards — px-4 sm:px-6 gutter + flex-wrap so the P&L drops below its label on narrow widths"
  - "Market-detail left column min-w-0 so the Recharts ResponsiveContainer price-history chart cannot force the grid past the viewport"
  - "Market-card footer min-w-0/truncate meta + shrink-0 source badge so long volume/deadline strings shrink instead of pushing the badge off-screen"
affects: [11-hardening-operator-demo-gate]

# Tech tracking
tech-stack:
  added:
    - "(none — Tailwind className / container-width edits only; no package install, no new component, no route, no prop, no data fetch)"
  patterns:
    - "SC#1 is CSS/layout-only (CONSTRAINT 1 / RESEARCH Pitfall 6): every diff hunk is a Tailwind className or container-width change. NO prop signature change, NO added/removed import, NO changed fetch/await/data call, NO new component, NO behavior change. A 'responsive' diff that adds/removes props or splits components has crossed the refactor line — explicitly avoided."
    - "Tailwind v4 is mobile-first; unprefixed = mobile (>=360px), sm:=640 md:=768 lg:=1024. The pages already used the right primitives (max-w-6xl mx-auto px-4 sm:px-6, grid-cols-1 sm:grid-cols-2 lg:grid-cols-3), so this was an AUDIT-AND-PATCH pass, not a rebuild. No tailwind.config exists and none was created (v4 CSS-first @theme in globals.css)."
    - "The Recharts-in-CSS-grid overflow fix is min-w-0 on the grid/flex column that holds the ResponsiveContainer — grid items default to min-width:auto, so a wide chart child can otherwise force the whole grid past the viewport at 360px."
    - "The overflow-prevention idiom for a justify-between row with a long string + a fixed control: min-w-0 + truncate on the text child (it shrinks first) + shrink-0 (and whitespace-nowrap for a money string) on the control (it never collapses or wraps mid-number)."

key-files:
  created:
    - ".planning/phases/11-hardening-operator-demo-gate/11-05-SUMMARY.md (this partial summary — Task 1 done, Task 2 pending)"
  modified:
    - "frontend/src/app/wallet/page.tsx (px-4 sm:px-6 gutter; transaction <li> gap-3 + min-w-0/truncate reason column + shrink-0/whitespace-nowrap amount)"
    - "frontend/src/app/portfolio/page.tsx (px-4 sm:px-6 gutter; both card rows flex-wrap gap-x-3 gap-y-1 + min-w-0 label so the P&L wraps below its label on narrow widths)"
    - "frontend/src/app/markets/[slug]/page.tsx (min-w-0 on the left lg:col-span-2 flex column so the Recharts price-history chart cannot force the grid past the viewport)"
    - "frontend/src/components/market-card.tsx (footer gap-2 + min-w-0/truncate meta div + shrink-0 source-badge wrapper)"
    - ".planning/STATE.md (Current Position — 11-05 in-progress / awaiting human-verify; NOT advanced to complete)"

key-decisions:
  - "Verify gate satisfied via `pnpm typecheck` (exit 0), NOT `pnpm build`: the frontend build is environmentally broken in this deep-path Windows worktree — `pnpm build` (Turbopack) fails IDENTICALLY on pristine HEAD with ~10 @radix-ui/* + @sentry/nextjs module-not-found errors (DEF-FE-BUILD-01, the same class 11-04 documented). It is NOT caused by these edits, and the real CI (frontend-ci.yml, clean shallow checkout) builds fine (proven on PR #16). Correctness here is established by typecheck (exit 0) + a strict hunk-by-hunk CSS-only diff review."
  - "Four of the eight files in files_modified needed NO change — they were already correct mobile-first at 360-768px: frontend/src/app/page.tsx (w-full max-w-6xl mx-auto px-4 sm:px-6), frontend/src/components/market-list.tsx (grid-cols-1 sm:grid-cols-2 lg:grid-cols-3), frontend/src/app/(auth)/layout.tsx (min-h-screen flex centered + Card w-full max-w-md + p-6), frontend/src/components/order-entry-form.tsx (full-width Select/Input via h-11 block defaults + w-full submit). Leaving a correct surface unchanged is the right call under CONSTRAINT 1 (no gratuitous edits)."
  - "The BetConfirmDialog (frontend/src/components/bet-confirm-dialog.tsx) is NOT in files_modified and was left untouched. Its DialogContent is `w-full max-w-lg` (fixed-centered, translate-x-[-50%]) which is capped at the viewport and CANNOT produce horizontal scroll at 360px (it goes edge-to-edge but never overflows). The plan says touch the dialog only IF it overflows (add max-w-[calc(100vw-2rem)]) — it does not, and it is out of the file-scope, so no change."
  - "frontend/src/app/layout.tsx is NOT in the diff — it is the exclusive-ownership boundary with plan 11-04 (the footer). Verified absent from `git diff --name-only`."

requirements-completed: []  # PLT-07 is NOT closed by this plan: the SC#1 phase-gate stays open until the Task-2 human visual-QA passes at 360/390/414/768px.

# Metrics
metrics:
  duration: ~15min
  completed: 2026-06-02
  tasks_done: 1
  tasks_pending: 1
  commits: 1
---

# Phase 11 Plan 05: Responsive QA (SC#1 / PLT-07) Summary

**One-liner:** Audited the six player-facing surfaces (home, market detail, bet flow, portfolio, wallet history, auth) at 360-768px and applied Tailwind-class/container-width-only fixes so none overflow horizontally — wallet + portfolio gutters dropped to `px-4 sm:px-6`, the wallet transaction rows and portfolio P&L rows now shrink/wrap their long strings (`min-w-0`/`truncate`/`flex-wrap`) while keeping money intact (`shrink-0`/`whitespace-nowrap`), the market-detail left column got `min-w-0` so the Recharts chart cannot push the grid past the viewport, and the market-card footer shrinks its volume/deadline meta instead of shoving the source badge off-screen; home, market-list, auth, and order-entry were already mobile-first and untouched.

## Status: IN-PROGRESS (autonomous work done; blocking human gate pending)

- **Task 1 (auto) — DONE.** Responsive CSS/layout-only fixes across the six player surfaces. Commit `dac111e`. Verified `pnpm typecheck` exit 0 + a hunk-by-hunk diff review proving every change is a Tailwind className / container-width change.
- **Task 2 (checkpoint:human-verify, gate=blocking) — PENDING.** Visual responsive QA at 360/390/414/768px (no horizontal scroll, thumb-reachable, readable). NOT executed — this is a blocking human gate; the plan is intentionally NOT marked complete (batched-checkpoint mode).

## What Was Built

### Task 1 — Responsive audit + CSS/layout-only fixes (commit `dac111e`)

Audited all eight files in `files_modified` against the 360 / 390 / 414 / 768px goal. **Four needed a fix; four were already correct.**

**Fixes applied (4 files, 18 insertions / 16 deletions, all `className`-only):**

- **`frontend/src/app/wallet/page.tsx`** — (a) page gutter `px-6` → `px-4 py-12 sm:px-6` (tighter 360px gutters, matches the home-page convention). (b) Transaction `<li>` `flex items-center justify-between` → added `gap-3`; the left kind/reason column got `min-w-0` and the reason `<span>` got `truncate` so a long reason shrinks instead of forcing scroll; the right amount column got `shrink-0` and the amount text got `whitespace-nowrap` so the money value never collapses or wraps mid-number.
- **`frontend/src/app/portfolio/page.tsx`** — (a) page gutter `px-6` → `px-4 py-12 sm:px-6`. (b) Both `CardContent` rows (`If this outcome wins` + `Realized P&L`) `flex items-center justify-between` → `flex flex-wrap items-center justify-between gap-x-3 gap-y-1`, with `min-w-0` on the label span, so on a narrow viewport the P&L drops cleanly below its label instead of overflowing.
- **`frontend/src/app/markets/[slug]/page.tsx`** — the LEFT grid column `flex flex-col gap-8 lg:col-span-2` → added `min-w-0`. A CSS-grid item defaults to `min-width: auto`, so the Recharts `ResponsiveContainer` price-history chart could otherwise force the column (and the whole grid) wider than a 360px viewport → horizontal scroll. `min-w-0` is the canonical fix. The header was already `flex flex-wrap items-center gap-3` and the grid already `grid-cols-1 lg:grid-cols-3` (stacks below lg) — no change needed there.
- **`frontend/src/components/market-card.tsx`** — footer `flex justify-between items-end` → added `gap-2`; the meta `div` (Vol + `|` + deadline) got `min-w-0 truncate` so a long volume/deadline string shrinks first, and the source-badge wrapper got `shrink-0` so the badge stays put rather than being pushed off-screen at 360px. The question title already uses `line-clamp-3` (fine).

**No fix needed (4 files — already correct mobile-first, verified by inspection at 360/768):**

- **`frontend/src/app/page.tsx`** — `w-full max-w-6xl mx-auto px-4 sm:px-6 py-12` (already mobile-first gutters + capped width).
- **`frontend/src/components/market-list.tsx`** — `grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3` (already single-column at 360px, multi-column above).
- **`frontend/src/app/(auth)/layout.tsx`** — `min-h-screen flex items-center justify-center … p-6` + `Card className="w-full max-w-md"` (already centered, width-capped, full-width-with-padding; auth forms are simple and fit).
- **`frontend/src/components/order-entry-form.tsx`** — the Select trigger + stake Input are block/full-width by default (`h-11`), the "Expected payout" row is a short-label `justify-between`, and the submit button is `w-full` (already thumb-reachable + non-overflowing).

**Task 1 verify:**
- `pnpm typecheck` (`tsc --noEmit`) → **exit 0** (ran via `npx pnpm@9.15.0 typecheck` against the present `node_modules`).
- `pnpm build` deliberately NOT used as the gate — see the key-decision above and the Deviation below (DEF-FE-BUILD-01: environmental Turbopack/pnpm-symlink failure identical on pristine HEAD; real CI builds clean).
- Diff review: `git diff` shows **4 files, 18 ins / 16 del, every hunk a Tailwind `className` change**. No prop signature changed, no import added/removed, no fetch/`await`/data call changed, no component added/removed.
- `frontend/src/app/layout.tsx` is **NOT** in `git diff --name-only` (11-04 ownership boundary). ✓
- `git status --short` shows only the four intended files. ✓
- `grep sm:px-6` present in both `wallet/page.tsx` (line 101) and `portfolio/page.tsx` (line 106). ✓

## Deviations from Plan

**1. [Out of scope — anticipated by the execution brief; verify gate uses typecheck not build] `pnpm build` is environmentally broken in this worktree (DEF-FE-BUILD-01)**
- **Found during:** Task 1 verification planning.
- **Issue:** The plan's `<automated>` verify is `pnpm typecheck && pnpm build`. `pnpm build` (Next.js Turbopack) fails in THIS deep-path Windows worktree with ~10 `@radix-ui/*` + `@sentry/nextjs` module-not-found errors that reproduce IDENTICALLY on pristine HEAD (a Windows pnpm-symlink + deep-worktree-path issue, the same class CLAUDE.md flags for PMS and that 11-04 logged as DEF-FE-BUILD-01). It is NOT caused by these CSS edits (none of the error modules are touched), and the real CI (`frontend-ci.yml`, clean shallow checkout) builds fine (proven green on PR #16).
- **Action:** Per the executor SCOPE BOUNDARY rule (pre-existing failures in unrelated files are logged, not chased) and the explicit execution-environment instruction, the verify gate is established by **`pnpm typecheck` (exit 0)** PLUS a strict hunk-by-hunk diff review proving every change is a Tailwind `className` / container-width change. The local build was NOT chased and the plan is NOT marked failed for it (it is environmental, not an implementation gap). Already tracked as DEF-FE-BUILD-01 in `deferred-items.md` (logged by 11-04).
- **Files modified:** none (decision only).

No other deviations — Task 1 executed as written. No Rule 1/2/3 auto-fixes were needed (the edits are pure presentation); no architectural (Rule 4) decisions arose.

## Known Stubs

None. This plan adds no data, no placeholder values, and no unwired components — it only adjusts Tailwind classes on already-shipped, already-wired surfaces.

## Pending: Task 2 — Visual responsive QA (blocking human gate)

Task 2 is a `checkpoint:human-verify` with `gate="blocking"`. Per the batched-checkpoint mode, the autonomous work (Task 1) shipped now; this blocking human gate is returned for the authoritative visual check and the plan is NOT marked complete. Responsive correctness is inherently visual and cannot be unit-asserted (RESEARCH / VALIDATION: manual-verify).

**How to verify (verbatim from the plan):** Run the frontend (dev server or built app) and, in browser device mode (and ideally one real mobile browser — iOS Safari or Android Chrome), check each surface at **360, 390, 414, and 768px**:
1. **Home (`/`)** — market list: no horizontal scroll; long market questions wrap/truncate; cards stack to one column at 360px.
2. **Market detail (`/markets/[slug]`)** — question header, resolution criteria, price-history chart, and order panel all fit; chart does not force horizontal scroll; order panel stacks below the content at narrow widths.
3. **Bet flow (order-entry form + confirm dialog)** — inputs full-width, confirm dialog fits 360px, buttons thumb-reachable.
4. **Portfolio (`/portfolio`)** — open + settled cards: stake/odds/P&L readable, no overflow.
5. **Wallet history (`/wallet`)** — balance + transaction rows: amounts readable, no overflow.
6. **Auth (`/login`, `/register`, `/forgot-password`, `/reset-password`, `/verify-email`)** — forms centered, inputs full-width, no overflow.

Confirm **NO horizontal scroll** on any surface at any tested width and **all controls are thumb-reachable**.

**Resume signal (verbatim from the plan):** Type **"approved"** if all six surfaces pass 360-768px, or list the surface + width + issue for a follow-up CSS-only fix.

## Commits

- `dac111e` — fix(11-05): responsive CSS pass for player surfaces (360-768px)

(This partial SUMMARY + the STATE update will be captured in a follow-up docs commit.)

## Self-Check: PASSED

- All modified files exist: frontend/src/app/wallet/page.tsx, frontend/src/app/portfolio/page.tsx, frontend/src/app/markets/[slug]/page.tsx, frontend/src/components/market-card.tsx, .planning/phases/11-hardening-operator-demo-gate/11-05-SUMMARY.md.
- Commit present in git log: `dac111e`.
- `frontend/src/app/layout.tsx` absent from the diff (11-04 boundary held).
