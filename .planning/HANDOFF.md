# HANDOFF — live operational state

> **Updated:** 2026-06-05 (Phase 15 closeout) · **Milestone:** v1.2 Credible Catalog · **Phase 15 of 18 — executed, code-reviewed, verified 13/13; branch NOT pushed — push + PR pending**
> Read this first. STATE.md + ROADMAP.md are the formal GSD truth; this is the live "what's happening NOW + what NOT to touch."
> Verify live state from git (`git log`, `origin/main`, `gh pr ...` once a PR exists), not these docs alone — they can drift.

---

## TL;DR

**Phase 15 (Event Settlement — House Resolve/Void + Mirrored Verify) is COMPLETE from an engineering standpoint: executed (3/3 plans), code-reviewed (1 critical + 4 warnings found AND fixed), and verified 13/13 must-haves / 5-of-5 requirements / 4-of-4 success criteria.** All work is committed on `gsd/phase-15-event-settlement-house-resolve-void-mirrored-verify`. **The branch is NOT pushed yet — the only remaining action is push + open 1 PR (only Pol merges).** No code work remains in Phase-15 scope.

---

## Phase 15 — exact status

- **Branch:** `gsd/phase-15-event-settlement-house-resolve-void-mirrored-verify` (forked clean off `origin/main` @ `1437257` = the #28 merge). **NOT pushed to origin.**
- **Delivers (EVT-06 + EVA-03..06):** a NEW `backend/app/settlement/event_service.py` (the ONLY production file) — `EventService.resolve_event` / `void_event` / `reverse_event` LOOP the UNCHANGED `SettlementService.resolve_market` / `reverse_settlement` over a `MarketGroup`'s children, **one FRESH `_get_session_maker()` session per child** (Option A — the 23505 dangling-tx landmine forbids chaining two self-committing settles on one session). Plus the pure, column-free `derive_event_status(children)` projection (EVT-06 — no migration, no authoritative status/winning_outcome column). Void = every child on NO (not a refund); reverse = compensating `reverse_settlement` per settled child, per-child `CHECK(balance>=0)` floor isolation; mirrored (`source=POLYMARKET`) groups are admin-rejected and auto-settle only through the existing `detect_polymarket_resolutions` path. **Purely additive: settlement primitives + `tasks.py` + migrations are byte-for-byte unchanged (0 diff vs `e9a4ac4`).**
- **Tests:** 3 new test files (`test_derive_event_status.py` 8 · `test_event_service.py` 18 · `test_event_mirrored.py` 2) = **28 passed** (per-module). Every resolution path asserts the spike-004 `reconcile._reconcile_async` `drift_count == 0`. ruff + `mypy app/settlement/event_service.py` clean.
- **Code review** (`15-REVIEW.md`, status `resolved`): found + fixed **CR-01** (resolve_event accepted a non-YES `winning_outcome_id` → would settle every child on NO while auditing `event.resolved`; now validates the YES leg via `_yes_outcome_id`), **WR-01/WR-04** (best-effort + audit-write failures now `logger.exception(...)` — no silent swallow in financial code), **WR-02/WR-03** (added the reverse blank-justification + NO-outcome-rejection tests). IN-01 (opaque `scalar_one()` error) + IN-02 (test-helper `conftest.py` dedup) deferred (info, non-blocking). Fix commit `5c2add9`.
- **Verification** (`15-VERIFICATION.md`): status `passed`, **13/13 must-haves**, 5/5 reqs, 4/4 success criteria — verified against the real code + git invariants.

## Pending — the only remaining action

1. **Push the branch + open 1 PR** (`gsd/phase-15-event-settlement-house-resolve-void-mirrored-verify` → `main`). `main` is protected, PR-only — **only Pol merges.** Open via the GitHub MCP `create_pull_request` from a **repo-rooted** session (the worktree session this was built in may lack the MCP tool — the documented GOTCHA). Engineering is done; this is a push/review/approval gate.
2. **Per the Phase-14 lesson — AUDIT the PR before declaring merge-ready:** re-check vs `origin/main` drift (none expected — clean fork), confirm CI is *actually* green via `gh pr checks` (the **Linux `backend` job** is the source of truth — the full `uv run pytest` + ruff + mypy; the Windows worktree full-suite flake is environmental, NOT code), and run a multi-lens audit. "PR opened ≠ done."

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
