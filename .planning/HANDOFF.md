# HANDOFF — live operational state

> **Updated:** 2026-06-05 (session close) · **Milestone:** v1.2 Credible Catalog · **Phase 13 of 18 done**
> Read this first. STATE.md + ROADMAP.md are the formal GSD truth; this is the live "what's happening NOW + what NOT to touch."

---

## TL;DR

**Phase 13 (Multi-outcome Model & Catalog Indexes) is COMPLETE, verified, and MERGED to `main`** (PR #25, 2026-06-05).
One follow-up PR is **open and waiting on Pol**: **#26 (backend CI green)** — all checks green, just needs Pol's merge.
**Phase 14 is ready to plan** but should start in a NEW session, ideally after #26 is merged.

---

## Phase 13 — exact status

- **Shipped:** migration `0011_phase13_market_groups` (additive `market_groups` table + nullable `Market.group_id`/`group_item_title` + `pg_trgm` + 6 catalog indexes), the `MarketGroup` ORM model + `Market.group` seam, and full tests. Requirement **EVT-01** closed (resolves v1.0 `MKT-08`).
- **Verified:** `13-VERIFICATION.md` = PASSED (4/4 must-haves). Code review = 0 blockers; 2 test-soundness warnings fixed pre-merge.
- **Merged:** PR [#25](https://github.com/polito101/xpredict/pull/25) → `main` @ `4e4b63e` (2026-06-05 10:35Z). All Phase 13 `.planning/` artifacts are on main.
- **Pure additive:** binary `Market`/`Outcome` model, the `trg_binary_outcomes_only` trigger, `SettlementService`, and all bet/odds/ledger paths are unchanged. Zero new deps.

## PR #26 — exact status (the ONE open thread)

- **Branch:** `chore/backend-ci-green` (off post-merge `main`). **PR [#26](https://github.com/polito101/xpredict/pull/26)** — state OPEN, mergeable, `BLOCKED` only on Pol's required review.
- **Why it exists:** `main`'s `backend` CI job was **pre-existing RED** (independent of Phase 13). Two fixes, both lint-only / zero behavior change:
  1. `1d26baf` — resolve ruff **F821** in `tests/settlement/test_resolve_market.py` (added `Market` under the existing `TYPE_CHECKING` block; the `-> Market` annotation referenced a function-local import). Pre-existing since a Phase 9 commit.
  2. `b921803` — `ruff format` on 3 drifted test files (`test_migration_0011.py`, `test_models.py` — the two Phase 13 tests whose format drift slipped past the Windows pre-commit hooks and landed via #25 — plus the settlement file). Canonical reflow, LF, no behavior change.
- **CI:** **#26 backend job = PASS (1m45s)** — ruff lint + ruff format-check + mypy(app/) + `pytest tests/ -x` ALL green on Linux. Every other check (bandit, gitleaks, pip-audit, pnpm-audit, dry-run, zap-baseline) green.

## CI status

- **`main` RIGHT NOW:** the `backend` job is **RED** (the F821 + format drift live on main until #26 merges). Everything else on main is green.
- **After Pol merges #26:** `main` backend CI goes fully GREEN. This is the single action that closes the loop.

## Open risks / blockers

1. **#26 must be merged by Pol** to make `main`'s backend CI green. CI signal for v1.2 (Phases 14-18) is unreliable until then. **No code risk — purely the merge.**
2. **Windows worktree is unreliable for backend verification** (this session's hard lesson): the full `uv run pytest` flakes (testcontainers connection contention) AND `ruff check`/`format` flip-flop (the worktree file set flickers 148↔202 between identical runs). **Always trust Linux CI for the backend, not the Windows worktree.** Verify locally per-module only.
3. **Carried-over (not new):** Phase 13's `deferred-items.md` logs **9 pre-existing ORM↔migration drifts** (non-Phase-13) — backlog, not blocking. Plus the standing v1.0/v1.1 deferred items in STATE.md (3 human-UAT, 3 missing VERIFICATION.md, and the **non-deferrable Spanish legal review** before any live operator demo).

## What NOT to touch

- Don't re-open / re-verify Phase 13 — it's merged and done.
- Don't try to "fix" the Windows full-suite test failures — they're environmental; Linux CI is the truth.
- Don't push to `main` or self-merge — PR-only; **only Pol merges**.

## Recommended Phase 14 starting point (do NOT start yet)

- **Phase 14 = Curated Per-Category Gamma Sync** (reqs CAT-01..06 + EVT-07): Gamma `/events` ingestion replaces the top-25-global poll; top-N-per-category with a ~7-tag allow-list + volume floor + dedup + keep-last-good; finally populates `Market.category` on mirrored rows. It **writes `market_groups` rows and stamps `group_id`** — i.e. it consumes exactly the Phase 13 seam.
- **Prereqs:** start from a fresh checkout of `main` **after #26 is merged** (so CI is green). New session, repo-rooted. Branch `gsd/phase-14-...`.
- **Kickoff:** `/gsd-autonomous --only 14` (single-phase, 1 PR — same flow that worked cleanly for Phase 13). Discuss → research → plan → execute → review → verify → ship.
- **Watch-outs for 14:** Gamma `/events` (not `/markets`) shape with embedded `markets[]` + `tags[]`; `len == 1` events stay on the standalone binary path (no group); the beat cadence for the events poll is slower (minutes) than the 30s odds poll.

---

*Note: the legacy `HANDOFF.json` in this directory is STALE (Phase 05, 2026-05-27) — ignore it; this `HANDOFF.md` supersedes it.*
