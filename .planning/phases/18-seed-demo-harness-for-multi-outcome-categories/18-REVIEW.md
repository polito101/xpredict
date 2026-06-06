---
phase: 18
status: clean
reviewers: 2
date: 2026-06-06
---

# Phase 18 — Code Review

**Method:** two independent adversarial read-only reviews of the committed range `e627224..HEAD`
(seed `bin/seed_demo.py` + `tests/seed/test_seed_demo_e2e.py` + `Makefile`), with distinct lenses —
(A) ledger / transaction correctness, (B) robustness / determinism / test quality. Both read the
change plus the services it calls (`event_service.py`, `service.py`, `reconcile.py`, `catalog/service.py`)
and the FK web (markets/wallet/auth models + migrations).

## Verdict: CLEAN

**No BLOCKER / HIGH / MEDIUM-correctness defects.** Every load-bearing invariant was verified to HOLD:

| Invariant | Status | Evidence |
|---|---|---|
| Money discipline (Decimal-from-string; all value movement via validated services) | ✅ HOLD | no hand-written ledger row / raw balance / float money in the change; odds = Numeric(8,6) probability, not money |
| 23505 dangling-tx landmine (session-per-self-committing-call) | ✅ HOLD | `create_house_event` (commits) on its own session; `place_bet` / `resolve_market` one fresh session each; `resolve_event`/`void_event` open their own per-child sessions |
| resolve_event CR-01 (winning_outcome_id = winner's YES) | ✅ HOLD | `seed_event_resolutions` passes `designated_child.yes_outcome_id`; partial path uses single-child `resolve_market` on the NO leg → derives `partially_resolved` |
| Reset CASCADE (DEMO-04) | ✅ HOLD | `markets` + `market_groups` co-truncated in one `TRUNCATE … CASCADE`; TRUNCATE doesn't honor `ON DELETE SET NULL` so co-truncation is REQUIRED and correct; house singletons re-seeded |
| Integrity stays green | ✅ HOLD | every event value movement is an ACID service tx; reconcile checks per-account self-consistency, excludes house_promo; baseline-relative drift==baseline in every test |
| No wallet overdraw | ✅ HOLD | worst case (default n_users=10) = user 3 stakes 850 vs 1000 funded (margin 150); verified across all configs incl. 20k random child-order permutations |

## Findings & resolutions

| # | Sev | Finding | Resolution |
|---|-----|---------|------------|
| 1 | MED | `_read_back_event_children` had no `ORDER BY` → child tuple order DB-arbitrary → event-bet stake/user assignment non-reproducible (contradicts the determinism contract). Cosmetic only (never overdraws, resolution is label-keyed). | **FIXED** — `.order_by(Market.group_item_title)`; the seed is now bit-deterministic. |
| 2 | MED | `test_seed_events_fill_featured_categories` queried the whole shared DB without resetting → a future coverage regression could pass on rows borrowed from earlier tests. | **FIXED** — `reset_demo()` first; the ≥2-per-tab assertion now proves THIS seed fills every featured tab and fails loud on regression. |
| 3 | LOW | In a sync-populated prod DB (~1900 mirrored markets), `list_catalog`'s `LIMIT 100` (no ORDER BY before cap, pre-existing Phase-16 behavior) could crowd the marquee house events out of the default volume window. | **DOCUMENTED (no code)** — out of Phase-18 scope (merged Phase-16 module); DEMO-03 is met (tabs filled abundantly by sync; the featured events are pinned by stable `demo-evt-*` slugs → deep-linkable by the sales script). |
| 4 | LOW | Politics / Pop Culture clear the minimum with zero margin (1 standalone + 1 event = 2) at the default `n_markets=15`. | **MITIGATED** — finding #2's hermetic test now locks the ≥2 guarantee at the shipped config and fails loud if a future `n_markets`/template change drops a tab below the minimum. |
| 5 | NIT | `assert event.designated_child is not None` on the seed path would be stripped under `python -O`. | **FIXED** — explicit `raise RuntimeError`; asserts kept only as type-narrowing after the raise. |
| 6 | NIT | `cfg` unused in `seed_event_bets`. | **FIXED** — docstring notes it is accepted for API symmetry (matches `seed_odds_history`). |
| 7 | NIT | Partial state relies on the 1-YES/1-NO spread for winners-and-losers. | **FIXED** — clarifying comment added at the partial branch. |

**Post-fix:** ruff + mypy clean; 19/19 `tests/seed/` pass (29s, testcontainers). Fixes committed in `5c87c1d`.
