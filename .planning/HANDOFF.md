# HANDOFF — live operational state

> **Updated:** 2026-06-05 (session close, post-#26-merge) · **Milestone:** v1.2 Credible Catalog · **Phase 13 of 18 DONE**
> Read this first. STATE.md + ROADMAP.md are the formal GSD truth; this is the live "what's happening NOW + what NOT to touch."

---

## TL;DR

**Phase 13 (Multi-outcome Model & Catalog Indexes) is COMPLETE, verified, and MERGED to `main`** (PR #25).
The follow-up backend-CI-green PR (**#26**) is **also MERGED** — **`main` backend CI is GREEN.**
**There is NO pending gate. Phase 14 is ready to start in a NEW session.**

---

## Phase 13 — exact status

- **Shipped + merged:** PR [#25](https://github.com/polito101/xpredict/pull/25) (2026-06-05 10:35Z). Migration `0011_phase13_market_groups` (additive `market_groups` table + nullable `Market.group_id`/`group_item_title` + `pg_trgm` + 6 catalog indexes), the `MarketGroup` ORM model + `Market.group` seam, and full tests. Requirement **EVT-01** closed (resolves v1.0 `MKT-08`).
- **Verified:** `13-VERIFICATION.md` = PASSED (4/4 must-haves). Code review = 0 blockers; 2 test-soundness warnings fixed pre-merge.
- **Pure additive:** binary `Market`/`Outcome` model, the `trg_binary_outcomes_only` trigger, `SettlementService`, and all bet/odds/ledger paths are unchanged. Zero new deps.
- **Artifacts:** all Phase 13 `.planning/phases/13-multi-outcome-model-catalog-indexes/*` docs on main (CONTEXT, RESEARCH, VALIDATION, PATTERNS, 2 PLANs, 2 SUMMARYs, REVIEW, VERIFICATION, deferred-items).

## Backend CI fix — DONE (PR #26)

- PR [#26](https://github.com/polito101/xpredict/pull/26) `chore/backend-ci-green` — **MERGED** (2026-06-05 11:14Z, merge commit `ece3c61`). Fixed a PRE-EXISTING red `backend` CI on main (independent of Phase 13), lint-only / zero behavior change:
  1. ruff **F821** in `tests/settlement/test_resolve_market.py` (`Market` added under the existing `TYPE_CHECKING` block — the `-> Market` annotation referenced a function-local import; pre-existing since a Phase 9 commit).
  2. `ruff format` on 3 drifted test files (`test_migration_0011.py`, `test_models.py`, `test_resolve_market.py`).

## CI status

- **`main` (`ece3c61`):** `backend-ci` = **GREEN** (ruff lint + ruff format-check + mypy(app/) + full `pytest tests/ -x` on Linux), `security` + `prod-migration-dry-run` green. CI signal for v1.2 (Phases 14-18) is healthy.
- `backend-ci.yml` is **path-filtered** (`paths: backend/**` + the workflow file + `.gitleaks.toml`) — `.planning/`-only commits do NOT re-run it.

## Open risks / notes

1. **No blocking gate.** Phase 14 can start now from a fresh `main`.
2. **Windows worktree is unreliable for backend verification** (this session's hard lesson): the full `uv run pytest` flakes (testcontainers connection contention) AND `ruff check`/`format` flip-flop (the worktree file set flickers 148↔202 between identical runs). **Always trust Linux CI for the backend, not the Windows worktree.** Verify locally per-module only (`uv run pytest tests/markets/ -x`).
3. **Carried-over (not new):** Phase 13's `deferred-items.md` logs **9 pre-existing ORM↔migration drifts** (non-Phase-13) — backlog, not blocking. Plus the standing v1.0/v1.1 deferred items in STATE.md (3 human-UAT, 3 missing VERIFICATION.md, and the **non-deferrable Spanish legal review** of ToS/token policy before any live operator demo).

## What NOT to touch

- Don't re-open / re-verify Phase 13 — merged and done.
- Don't try to "fix" the Windows full-suite test/ruff failures — they're environmental; Linux CI is the truth.
- Don't push to `main` or self-merge — PR-only; **only Pol merges**.

## Recommended Phase 14 starting point

- **Phase 14 = Curated Per-Category Gamma Sync** (reqs CAT-01..06 + EVT-07): Gamma `/events` ingestion replaces the top-25-global poll; top-N-per-category with a ~7-tag allow-list + volume floor + dedup + keep-last-good; finally populates `Market.category` on mirrored rows. It **writes `market_groups` rows and stamps `group_id`** — i.e. it consumes exactly the Phase 13 seam.
- **Prereqs:** new session, repo-rooted (workspace = `Documents\XPredict\xpredict`, not home), from a fresh checkout of `main` (`ece3c61` or later, CI green). Branch `gsd/phase-14-...` (the GSD tooling auto-creates the full-slug branch — don't pre-create a short name).
- **Kickoff:** `/gsd-autonomous --only 14` (single-phase, 1 PR — same flow that worked cleanly for Phase 13). Discuss → research → plan → execute → review → verify → ship.
- **Watch-outs for 14:** Gamma `/events` (not `/markets`) shape with embedded `markets[]` + `tags[]`; `len == 1` events stay on the standalone binary path (no group); the beat cadence for the events poll is slower (minutes) than the 30s odds poll. Verify the phase on **Linux CI**, not the Windows worktree.
