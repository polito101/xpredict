---
phase: 14-curated-per-category-gamma-sync
audit: final pre-merge multi-lens hardening
date: 2026-06-05
status: resolved
lenses: 4
verdict: ready-for-merge
confidence: high
---

# Phase 14 — Final Pre-Merge Hardening Audit

A second, deeper pass after the standard code review (which found + fixed CR-01/CR-02). **Four opus reviewers, one per lens** — transactions/concurrency, Gamma ingestion/edge-cases, spec-vs-impl/tests, CI-Linux/prod/quality — each hunting what the first review missed. Every real finding was adversarially verified, fixed, and covered with **bidirectional** regression tests (pass on fix, fail on revert).

## Integration state (was blocking the merge — now resolved)
- **`origin/main` had advanced** (PR #27 merged) → PR #28 was `CONFLICTING`/`DIRTY`. Merged `origin/main` into the branch (`e0a7cb6`); conflicts were **only `.planning/` docs**, code untouched. Also repaired Windows **mojibake** (`â€"` → `—`) that `gsd-sdk roadmap` had introduced into `ROADMAP.md`. Branch is now **0 behind main**, clean merge, mergeable.
- **backend CI was RED**: `ruff format --check` failed on `test_adapter.py` + `test_tasks.py` (2 lines collapse < 100 chars, ruff 0.8.6). Fixed (`8f731fc`).

## Findings & resolutions

### CRITICAL — real bugs the first review missed (fixed `2062f11`, regression-tested `8628c7c`)
- **C-1 — NaN `volume24hr` nuked a whole category.** `_safe_decimal(nan)` built `Decimal('NaN')` (the `InvalidOperation` guard didn't fire on construction); the later floor `>= $10k` comparison then raised, caught per-category → the entire category's curated batch was silently discarded that tick. **Fix:** reject non-finite (`is_finite`) → floors out cleanly. **Bidirectional test:** reverting the guard fails 4 tests.
- **C-2 — blank/duplicate `conditionId` dropped real children/events.** `sync_events` deduped by `condition_id`, which Gamma leaves `""` on not-yet-deployed markets → a real child could be dropped, a multi-outcome event collapsed to standalone, or (all-blank) the event dropped entirely; the dedup key also didn't match the persistence key (`id`). **Fix:** dedup by market `id` (= `source_market_id`, always present). **Bidirectional test:** reverting to `condition_id` fails 2 tests with the exact failure mode (`synced==1`, collapsed).

### WARNING — fixed
- **W-1 — events-lock could expire mid-cycle.** Fixed 280s TTL, no renewal; a slow cycle (7 categories × Gamma retries) could exceed it → two cycles overlap (row-lock contention/deadlocks). **Fix:** TTL → 600s (> worst-case cycle); happy-path release stays immediate; a crash auto-recovers in ≤600s. Release was already owner-token-safe (no cross-owner delete).
- **Dead code / CAT-05 clarity.** Removed the unused `fetch_events(offset=...)` param + the dead "short-page stop" docstring; the 500 cap now reads `POLYMARKET_EVENTS_LIMIT_CAP` (no magic number); documented that **ranked top-N + same-metric (`volume24hr`) floor needs no pagination** — CAT-05 is complete by construction, not missing. Clarified `resolve_category` is **drift-logging only** (category routing is the fetched `tag_id`).

### Coverage gaps closed (new tests, `8628c7c`)
Volume-floor `>=` boundary · CAT-06 empty-category suppression · **keep-last-good durability against real Postgres** (the production-shape transaction the first review never integration-tested) · spike-002 OPEN-event-with-`1.0`-strike stays OPEN · fixed a self-contradictory test fixture (events now carry the tag of the category they're fetched under).

### Confirmed SAFE by the audit (suspicious-but-correct — explicitly cleared)
The CR-01/CR-02 fixes are correct; `begin_nested()` SAVEPOINT semantics on autobegin match the established `MarketService` pattern; nested-commit→outer-commit durability, poisoned-session cleanup, delta-publish ordering, and the slug-collision retry are all sound (6 patterns cleared); `_derive_status` correctly keeps OPEN-with-strike children OPEN; import-time `Settings()` is benign (env-gated, pre-existing); resource/lock cleanup is correct on every path; the CR-01/CR-02 regression tests are genuine (not false positives).

## Residual risks (real, accepted — disclosed for Pol)
1. **Lock TTL trade-off:** a *crashed* cycle now blocks sync for up to 600s (2 ticks); the catalog keeps last-good meanwhile. Acceptable vs the overlap risk.
2. **Float-derived event volume:** the floor compares `Decimal(str(float))`, inheriting float repr for the soft $10k credibility gate (not money, not a payout — curation only). Non-corruptive.
3. **W-2 (theoretical):** if Gamma ever returns an event under a `tag_id` filter without that tag in the event's `tags[]`, it's stamped with the fetched category and `resolve_category` logs drift. Not observed in live data.
4. **2 post-deploy human checks** (`14-HUMAN-UAT.md`): redbeat beat-restart + live `tag_id` drift — inherent to deploy, not verifiable pre-merge.
5. **Linux CI is the full-suite gate:** verified per-module locally (Windows-worktree testcontainers flake); ruff/mypy/per-module all green gives high confidence the Linux full suite passes.

## Verification
`ruff check` ✓ · `ruff format --check` ✓ · `mypy app/` (94 files) ✓ · **63 polymarket tests** (unit + integration) ✓ — all green locally; full suite + repo-wide ruff/mypy run on Linux CI.

## Verdict: READY FOR MERGE · Confidence: HIGH
