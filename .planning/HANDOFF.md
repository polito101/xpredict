# HANDOFF — live operational state

> **Updated:** 2026-06-05 (Phase 14 closeout) · **Milestone:** v1.2 Credible Catalog · **Phase 14 of 18 — executed, audited, PR #28 awaiting Pol's merge**
> Read this first. STATE.md + ROADMAP.md are the formal GSD truth; this is the live "what's happening NOW + what NOT to touch."
> Verify live state from git (`gh pr view 28`, `gh pr checks 28`, `origin/main`), not these docs alone — they can drift.

---

## TL;DR

**Phase 14 (Curated Per-Category Gamma Sync) is COMPLETE from an engineering standpoint: executed, verified 11/11, code-reviewed, hardened by a final 4-lens audit, and GREEN on backend CI. PR [#28](https://github.com/polito101/xpredict/pull/28) is OPEN + MERGEABLE — the ONLY thing left is Pol's review/merge.** No code work remains in Phase-14 scope.

---

## Phase 14 — exact status

- **Branch:** `gsd/phase-14-curated-per-category-gamma-sync` (HEAD `9e36246`, pushed; PR head == local head). 34 commits ahead of `origin/main`, **0 behind** (merged `origin/main` in — clean).
- **Delivers (CAT-01..06 + EVT-07):** Gamma `GET /events` per-category curated sync replaces the flat top-25 poll; writes `market_groups` rows + stamps `Market.group_id`/`group_item_title`/`category`; dedup → `volume24hr` floor → top-N; keep-last-good per category; `len==1` → standalone; beat swap `poll_polymarket_top25`@30s → `poll_polymarket_events`@300s. **Zero new deps.**
- **Verification:** `14-VERIFICATION.md` = 11/11 must-haves · 4/4 SC · 7/7 reqs (verified against real code). Status `human_needed` ONLY for 2 post-deploy checks (below) — NOT code gaps.
- **Code review** (`14-REVIEW.md`): found + fixed 2 blockers — CR-01 (child IntegrityError did a full-tx rollback orphaning the group → SAVEPOINT fix) and CR-02 (changed_markets not reset per category). Bidirectional regression tests added.
- **Final multi-lens audit** (`14-AUDIT.md`, 4 opus reviewers): found + fixed 2 more CRITICAL bugs the first review missed — **NaN `volume24hr`** (detonated the floor → `is_finite` guard) and **blank/duplicate `conditionId`** (dropped/collapsed events → dedup by market `id`). Plus lock-TTL race (280→600s) and dead-code cleanup. 7 regression/coverage tests added (CR-01/CR-02/NaN/conditionId bidirectional).
- **Local gate (full CI surface):** `ruff check` ✓ · `ruff format --check` ✓ · `mypy app/` (94 files) ✓ · 63 polymarket tests ✓.

## PR #28 — exact status (the ONE open thread)

- **State:** OPEN · `mergeable=MERGEABLE` · `mergeStateStatus=BLOCKED` (blocked ONLY by branch protection requiring Pol's review — NOT a conflict).
- **CI (all GREEN on head `9e36246`):** `backend` ✓ (1m37s — full `pytest tests/` + ruff lint + ruff format-check + mypy app/ on Linux), `bandit` ✓, `gitleaks` ✓, `pip-audit` ✓, `pnpm-audit` ✓, `prod-migration-dry-run` ✓, `zap-baseline` ✓.
- **No merge conflicts.** `HEAD` contains all of `origin/main` (post-#27); clean-merge probe = 0 markers.

## Pending — Pol (the only remaining action)

1. **Review + merge PR #28.** `main` is protected, PR-only — **only Pol merges.** Engineering is done; this is a review/approval gate.

## Pending — deploy (post-merge, tracked in `14-HUMAN-UAT.md`)

1. **Restart the beat process** on deploy — redbeat persists the schedule in Redis, so the swap (`poll_polymarket_top25`→`poll_polymarket_events`) is inert until beat restarts and re-syncs. Then confirm `poll_polymarket_events` fires @300s, top-25 no longer fires, and `market_groups` rows appear. (Code-side swap verified green by `test_beat_schedule_entries`; only the live reload is manual.)
2. **Re-verify the 7 `tag_id`s** at deploy via the live `GET /tags/slug/{slug}` loop (Politics=2, Sports=1, Crypto=21, Pop Culture=596, Economy=100328, Tech=1401, World=101970) — pinned 2026-06-05; a drifted id would mis-route/empty a category.

## Residual risks (real, accepted — documented in `14-AUDIT.md`)

- **Lock TTL=600s:** a *crashed* cycle blocks sync for ≤600s (catalog keeps last-good meanwhile). Conscious trade-off vs the overlap risk.
- **Float-derived event volume floor:** the $10k credibility gate compares `Decimal(str(float))` (soft curation threshold — not money/payouts). Non-corruptive.
- **W-2 (theoretical):** an event returned under a `tag_id` filter without that tag in its `tags[]` is stamped with the fetch category (+ drift-logged). Not observed in live data.
- Standing v1.0/v1.1 deferred items (in STATE.md): 3 human-UAT, 3 missing VERIFICATION.md, and the **non-deferrable Spanish legal review** of ToS/token policy before any live operator demo.

## CI / environment notes

- `backend-ci.yml` is **path-filtered** (`paths: backend/**` + the workflow file + `.gitleaks.toml`) — `.planning/`-only commits do NOT re-run the backend job, so this docs commit leaves the green backend result on `9e36246` intact.
- **Windows worktree is unreliable for backend verification:** the full `uv run pytest` flakes (testcontainers contention) AND `ruff check`/`format` flip-flop. **Trust Linux CI, not the Windows worktree.** Verify locally per-module only.

## What NOT to touch

- Don't re-open / re-verify / re-implement Phase 14 — it's engineering-complete; the only open action is Pol's merge of #28.
- Don't push to `main` or self-merge — PR-only; **only Pol merges**.
- Don't "fix" Windows full-suite test/ruff flip-flop — environmental; Linux CI is the truth.

## Recommended next session — Phase 15 (after #28 merges)

- **Phase 15 = Event Settlement (House Resolve/Void + Mirrored Verify)** — reqs EVT-06, EVA-03..06. `EventService` resolve-as-a-loop over the existing `SettlementService` per child; void = all-children-NO; reverse via compensating ledger; derived event status (no authoritative winning_outcome column); mirrored children auto-settle via the existing UMA detection (verify, no new code). Depends on Phase 13 (group model) + benefits from Phase 14's real mirrored data.
- **Prereq:** start ONLY after Pol merges #28, from a fresh `origin/main` checkout (so Phase 14's `market_groups` writer + sync are in main). New session, repo-rooted (workspace = `Documents\XPredict\xpredict`, not home).
- **Kickoff:** `/gsd-autonomous phase 15` (single-phase, 1 PR — same flow that worked for Phases 13 + 14). And per the Phase-14 lesson: after "ship", AUDIT the PR (re-check vs `origin/main` drift, confirm CI actually green via `gh`, run a multi-lens code audit) before declaring merge-ready.
- **Watch-outs for 15:** run the spike-004 double-entry integrity check green after every resolution path; never settle on `closed=true` alone (spike-002 guard); per-child transactions (Option A), idempotent replay; mirrored events stay admin-read-only except emergency force-settle.
