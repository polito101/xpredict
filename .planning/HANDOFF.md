# HANDOFF — live operational state

> **Updated:** 2026-06-06 (Phase 18 closeout — PR opened + CI 7/7 green) · **Milestone:** v1.2 Credible Catalog · **Phase 18 of 18 (LAST) — DONE: PR [#32](https://github.com/polito101/xpredict/pull/32) OPEN, CI 7/7 GREEN, MERGEABLE, 0 drift → MERGE READY, awaiting Pol's review/merge. v1.2 is ENGINEERING-COMPLETE.**
> Read this first. STATE.md + ROADMAP.md are the formal GSD truth; this is the live "what's happening NOW + what NOT to touch."
> Verify live state from git (`git log`, `origin/main`, `gh pr ...`), not these docs alone — they can drift.

---

## TL;DR

**Phase 18 (Seed/Demo Harness for Multi-outcome + Categories) is COMPLETE — the LAST v1.2 phase and the milestone's end-to-end integration acceptance test.** Extends `bin/seed_demo.py` through the MERGED service layer (zero new domain code) to seed one marquee multi-outcome event per canonical category, all four event states, non-flat per-outcome odds history, an idempotent `--reset`, and a green double-entry integrity check. Executed end-to-end autonomously (1 plan, 5 commits, +1103/-32 in 8 files), reviewed by 2 independent reviewers (money discipline / 23505 / resolve_event CR-01 / reset-CASCADE / integrity-green / no-overdraw = all HOLD → **CLEAN**; MED/LOW/NIT fixed), verified goal-backward (**PASSED**, DEMO-01..04). Shipped to **PR [#32](https://github.com/polito101/xpredict/pull/32)**: OPEN, **all 7 CI checks GREEN** (incl. `backend` 2m7s — full pytest+ruff+mypy on Linux), `mergeable=MERGEABLE`, **0 drift** vs `origin/main` (0 behind / 5 ahead). Only remaining action: **Pol's review/merge** (`reviewDecision=REVIEW_REQUIRED`; `main` is protected). **Status: MERGE READY.**

**v1.2 Credible Catalog is engineering-complete** — Phase 17 (PR #31) is **MERGED** into `origin/main` (`be4c635`/`e627224`), along with Phases 13 (#25), 14 (#28), 15 (#29), 16 (#30). Once Pol merges #32, all 6 v1.2 phases are on main → run the **milestone lifecycle** (`/gsd-audit-milestone` → `/gsd-complete-milestone` → `/gsd-cleanup`).

---

## Phase 18 — exact status

- **Branch / PR:** `gsd/phase-18-seed-demo-harness-for-multi-outcome-categories` (forked off `origin/main` @ `e627224`; **0 behind, 5 ahead**, no drift). **PR [#32](https://github.com/polito101/xpredict/pull/32) OPEN**, `mergeable=MERGEABLE`, `mergeStateStatus=BLOCKED` ONLY by `reviewDecision=REVIEW_REQUIRED`, Pol requested as reviewer. Opened via `gh` (the worktree session lacks the `create_pull_request` MCP — the documented GOTCHA; only Pol merges).
- **Delivers (DEMO-01..04; the milestone integration acceptance test):** extends `backend/bin/seed_demo.py` + `tests/seed/test_seed_demo_e2e.py` + `Makefile` — **no backend domain changes, no new deps.**
  - **Events** — one marquee multi-outcome house event per canonical category (Politics, Sports, Crypto, Pop Culture, Economy, Tech, World) via `EventService.create_house_event` (own session, commits once); 3–8 independent binary YES/NO children, plausible per-outcome YES prices (never sum-to-100 — framing LOCK). `_EVENT_TEMPLATES` + `build_event_specs` + `seed_events` + `_read_back_event_children` (ordered by label = deterministic).
  - **4 states** — `seed_event_resolutions`: resolved (`resolve_event` winner-YES/losers-NO) · void (`void_event` all-NO) · partial (single-child `SettlementService.resolve_market` on the NO leg → derives `partially_resolved`) · open (untouched). `seed_event_bets` = both-sides spread → winners AND losers.
  - **Odds** — event children reuse the `SeededMarket` shape, so `seed_odds_history` gives non-flat per-outcome history unchanged.
  - **Reset fix (DEMO-04)** — added `market_groups` to `_RESET_TABLES` (the FK points markets→groups, so TRUNCATE markets didn't cascade into groups → a re-seed of deterministic event slugs would collide on the UNIQUE slug). `verify_integrity()` surfaces the spike-004 reconcile in the CLI for seed + reset.
  - **DEMO-03** — `FEATURED_CATEGORIES` PINNED (hardcoded) + `_assert_featured_categories_match_canonical()` coherence guard vs `POLYMARKET_CATEGORIES` (drift-insulated); standalone templates retagged onto the canonical 7. `Makefile`: real `seed` + new `demo-reset`.
- **Tests:** 7 (4-state coverage · featured-category fill (hermetic) · non-flat odds · reset idempotency · acceptance · guard · reset) → **19/19 `tests/seed/` green** (testcontainers, ~29s); Linux CI `backend` job GREEN (full pytest + ruff + mypy, 2m7s).
- **Code review** (`18-REVIEW.md`, status `clean`, 2 reviewers): money discipline / 23505 session-per-call / resolve_event CR-01 / reset-CASCADE / integrity-green / no-overdraw = all HOLD. MED (deterministic child order, hermetic test), NIT (raise-not-assert) — **all fixed** (`5c87c1d`).
- **Verification** (`18-VERIFICATION.md`): status `passed`, all 4 success criteria + DEMO-01..04 traced to code + passing tests.

## Post-PR audit — DONE (the "PR opened ≠ done" gate)

- **Drift:** 0 behind `origin/main` (`e627224`), 5 ahead. No conflicts. ✓
- **CI: 7/7 GREEN** — `backend` ✓ (2m7s, full pytest+ruff+mypy), `dry-run` ✓, `gitleaks (full history)` ✓, `bandit` ✓, `pip-audit` ✓, `pnpm-audit` ✓, `zap-baseline` ✓. ✓
- **Mergeability:** `MERGEABLE`, `BLOCKED` only by the required review (Pol). ✓
- **Invariants:** seed/test-only — zero backend domain changes, zero new dependencies; every value movement through the validated services; reconcile green after seed AND reset. ✓

## Environment notes (Windows worktree)

- **Backend local validation per-module is authoritative here, NOT the full suite.** `ruff check`/`format` + `mypy` on the single changed file are stable; the targeted `uv run pytest tests/seed/` ran **19/19 green** (one module group = no cross-module testcontainer contention). The FULL `uv run pytest` flakes on this worktree (testcontainers contention across UNRELATED modules) — **trust Linux CI `backend`** as authoritative (it ran the full suite + ruff + mypy GREEN). See [[xprediction-backend-fullsuite-testcontainers-flake]].
- Execution ran INLINE (spawned `gsd-executor` agents stream-idle-timeout on this worktree; read-only review/discovery agents are fine).

## What NOT to touch

- Don't re-open / re-verify Phase 18 — engineering-complete; the only open action is Pol's merge of PR #32.
- Don't push to `main` or self-merge — PR-only; **only Pol merges**.
- Don't revert the `market_groups` addition to `_RESET_TABLES` — it's the DEMO-04 idempotency fix (without it a re-seed collides on the group slug).
- Per-outcome framing: NEVER introduce a stacked/normalized/sum-to-100 outcome bar (the gating invariant) — the seed's per-outcome YES prices are deliberately independent.
- Money discipline: never hand-write a ledger row / mutate `accounts.balance` / chain two self-committing services on one session (the 23505 landmine) in the seed.

## Recommended next session — milestone lifecycle (after #32 merges)

- **v1.2 Credible Catalog is engineering-complete** (all 6 phases 13–18 done; 29/29 P1 reqs). Once Pol merges PR #32 from a fresh `origin/main` checkout, run the milestone lifecycle: `/gsd-audit-milestone` → `/gsd-complete-milestone v1.2` → `/gsd-cleanup`.
- **Do NOT start any new milestone / phase** until Pol merges and the lifecycle runs.
- Advisory carried forward (pre-existing, out of Phase-18 scope): in a sync-populated prod DB the marquee house events may rank below ~1900 mirrored markets in the default volume sort — they remain reachable by their pinned `demo-evt-*` slugs (deep-linkable by the sales script); if list prominence is needed, that's a Phase-16 catalog ordering change for a future milestone.

## Standing deferred items (carried from v1.0/v1.1, unchanged)

| Category | Item | Status |
|----------|------|--------|
| legal (gating) | Spanish counsel review of ToS + token policy | Open — **not deferrable** before any live operator demo |
| human-UAT | Phase 12 `12-HUMAN-UAT.md` | 3 scenarios open |
| verification | Phases 03 / 04 / 05 | 3 VERIFICATION.md missing (backends shipped) |
| backend (Phase 17 follow-up) | Dedicated admin event-list endpoint + editable `resolution_criteria` on `UpdateEventRequest` | Deferred — Phase 17 UI uses the public catalog (house-filtered) for the admin list; criteria not editable post-create |
