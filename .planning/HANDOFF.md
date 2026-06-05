# HANDOFF — live operational state

> **Updated:** 2026-06-05 (Phase 15 closeout — PR opened + CI green) · **Milestone:** v1.2 Credible Catalog · **Phase 15 of 18 — DONE: PR [#29](https://github.com/polito101/xpredict/pull/29) OPEN, CI 7/7 GREEN, MERGEABLE → MERGE READY, awaiting Pol's review/merge**
> Read this first. STATE.md + ROADMAP.md are the formal GSD truth; this is the live "what's happening NOW + what NOT to touch."
> Verify live state from git (`git log`, `origin/main`, `gh pr ...` once a PR exists), not these docs alone — they can drift.

---

## TL;DR

**Phase 15 (Event Settlement — House Resolve/Void + Mirrored Verify) is COMPLETE: executed (3/3 plans), code-reviewed (1 critical + 4 warnings found AND fixed), verified 13/13 must-haves / 5-of-5 requirements / 4-of-4 success criteria — and shipped to PR [#29](https://github.com/polito101/xpredict/pull/29).** **The PR is OPEN, all 7 CI checks are GREEN, `mergeable=MERGEABLE` with 0 drift vs `origin/main` — the only remaining action is Pol's review/merge** (`reviewDecision=REVIEW_REQUIRED`; `main` is protected, only Pol approves+merges). No code work remains in Phase-15 scope. **Status: MERGE READY.**

---

## Phase 15 — exact status

- **Branch / PR:** `gsd/phase-15-event-settlement-house-resolve-void-mirrored-verify` (forked clean off `origin/main` @ `1437257` = the #28 merge). **PR [#29](https://github.com/polito101/xpredict/pull/29) OPEN** (22 commits ahead, 0 behind — no drift); `mergeable=MERGEABLE`, `mergeStateStatus=BLOCKED` ONLY by `reviewDecision=REVIEW_REQUIRED` (branch protection awaiting Pol's approval — NOT a conflict). Opened via `gh` (the worktree session lacked the `create_pull_request` MCP — the documented GOTCHA; repo CLAUDE.md permits `gh pr create`; only Pol merges).
- **Delivers (EVT-06 + EVA-03..06):** a NEW `backend/app/settlement/event_service.py` (the ONLY production file) — `EventService.resolve_event` / `void_event` / `reverse_event` LOOP the UNCHANGED `SettlementService.resolve_market` / `reverse_settlement` over a `MarketGroup`'s children, **one FRESH `_get_session_maker()` session per child** (Option A — the 23505 dangling-tx landmine forbids chaining two self-committing settles on one session). Plus the pure, column-free `derive_event_status(children)` projection (EVT-06 — no migration, no authoritative status/winning_outcome column). Void = every child on NO (not a refund); reverse = compensating `reverse_settlement` per settled child, per-child `CHECK(balance>=0)` floor isolation; mirrored (`source=POLYMARKET`) groups are admin-rejected and auto-settle only through the existing `detect_polymarket_resolutions` path. **Purely additive: settlement primitives + `tasks.py` + migrations are byte-for-byte unchanged (0 diff vs `e9a4ac4`).**
- **Tests:** 3 new test files (`test_derive_event_status.py` 8 · `test_event_service.py` 18 · `test_event_mirrored.py` 2) = **28 passed** (per-module). Every resolution path asserts the spike-004 `reconcile._reconcile_async` `drift_count == 0`. ruff + `mypy app/settlement/event_service.py` clean.
- **Code review** (`15-REVIEW.md`, status `resolved`): found + fixed **CR-01** (resolve_event accepted a non-YES `winning_outcome_id` → would settle every child on NO while auditing `event.resolved`; now validates the YES leg via `_yes_outcome_id`), **WR-01/WR-04** (best-effort + audit-write failures now `logger.exception(...)` — no silent swallow in financial code), **WR-02/WR-03** (added the reverse blank-justification + NO-outcome-rejection tests). IN-01 (opaque `scalar_one()` error) + IN-02 (test-helper `conftest.py` dedup) deferred (info, non-blocking). Fix commit `5c2add9`.
- **Verification** (`15-VERIFICATION.md`): status `passed`, **13/13 must-haves**, 5/5 reqs, 4/4 success criteria — verified against the real code + git invariants.

## Pending — the only remaining action (Pol)

1. **Pol: review + merge PR [#29](https://github.com/polito101/xpredict/pull/29).** `main` is protected, PR-only — only Pol approves+merges. Everything automatable is done: PR open, CI green, mergeable, no drift, technical review complete.

## Post-PR validation — DONE (the Phase-14 "audit before merge-ready" gate)

- **Drift:** 0 behind `origin/main` (22 ahead) — clean fork, no drift. ✓
- **CI: 7/7 GREEN** on the PR head — `backend` ✓ (full Linux `uv run pytest` + ruff + mypy, 1m50s), `bandit` ✓, `pip-audit` ✓, `pnpm-audit` ✓, `gitleaks (full history)` ✓, `prod-migration-dry-run` ✓, `zap-baseline` ✓. The Linux `backend` job confirms the whole suite green — the Windows-worktree full-suite flake was environmental, as expected. ✓
- **Mergeability:** `mergeable=MERGEABLE`, no conflicts; `BLOCKED` only by the required review (Pol's approval). ✓
- **Technical review:** code-review (CR-01 + 4 warnings fixed) + verifier (13/13) + a final red-flag scan of the diff (no debug/skips/secrets/stray files). ✓
- **Invariants:** purely additive — 1 new prod file; settlement primitives + `tasks.py` + migrations 0 diff. ✓

## CI / environment notes

- **Windows worktree is unreliable for full-suite backend verification:** the full `uv run pytest` flakes (testcontainers contention across unrelated modules) AND `ruff check`/`format` flip-flop on the full file set. **Verify per-module (settlement) locally; trust Linux CI for the full suite + ruff + mypy.** (Phase 15 was verified per-module green; CI will confirm the whole suite.)
- **Execution ran with `workflow.use_worktrees=false`** to avoid nesting a git worktree inside the Windows agent worktree (the documented breakage). That config toggle was reverted (not committed) — the PR contains only the settlement code + tests + `.planning/` docs.

## What NOT to touch

- Don't re-open / re-verify / re-implement Phase 15 — it's engineering-complete; the only open action is push + Pol's merge.
- Don't push to `main` or self-merge — PR-only; **only Pol merges**.
- Don't "fix" the Windows full-suite test/ruff flip-flop — environmental; Linux CI is the truth.
- Don't modify `SettlementService` / `tasks.py` / migrations — Phase 15 deliberately left them byte-for-byte unchanged (the whole point: compose, don't reinvent).

## Recommended next session — Phase 16 (after #15's PR merges)

- **Phase 16 = Catalog & Event API + House Event CRUD** — reqs BRW-01..06, CAT-01..06, EVA-01/02, EVT-01..05/07 (the HTTP contract: browse/search/category/event reads + house-event create/edit/resolve/reverse). Depends on Phase 15 (the resolve/reverse service is the admin event API's engine). The EVA-03 two-step confirm + admin auth surface deferred from Phase 15 lands here.
- **Prereq:** start ONLY after Pol merges the Phase-15 PR, from a fresh `origin/main` checkout. New session, repo-rooted (workspace = `Documents\XPredict\xpredict`, not home) so the GitHub MCP loads.
- **Kickoff:** `/gsd-autonomous phase 16` (single-phase, 1 PR — the same flow that worked for 13/14/15).

## Standing deferred items (carried from v1.0/v1.1, unchanged)

| Category | Item | Status |
|----------|------|--------|
| legal (gating) | Spanish counsel review of ToS + token policy | Open — **not deferrable** before any live operator demo |
| human-UAT | Phase 12 `12-HUMAN-UAT.md` | 3 scenarios open |
| verification | Phases 03 / 04 / 05 | 3 VERIFICATION.md missing (backends shipped) |
