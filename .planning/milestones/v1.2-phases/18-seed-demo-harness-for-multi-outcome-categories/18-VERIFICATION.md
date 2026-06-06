---
phase: 18
status: passed
requirements: [DEMO-01, DEMO-02, DEMO-03, DEMO-04]
date: 2026-06-06
---

# Phase 18 — Verification (goal-backward)

**Phase goal:** One command seeds a credible multi-outcome demo across every category and every
event state, and the reset is idempotent with a green integrity check — exercising every prior
phase (model → sync → settlement → API → UI) as the milestone's integration acceptance test.

**Method:** goal-backward — each success criterion / DEMO requirement traced to code + a passing
test (`backend/tests/seed/test_seed_demo_e2e.py`, run against a real Postgres via testcontainers).
**Local evidence:** `uv run pytest tests/seed/ -q` → **19 passed in 29s** (7 e2e + 12 standalone),
ruff + mypy clean on `bin/seed_demo.py`.

## Success criteria

| SC | Requirement | TRUE? | Proof |
|----|-------------|-------|-------|
| **SC1** ≥1 multi-outcome event per category, 3–8 outcomes, plausible per-outcome YES prices | DEMO-01 | ✅ | `_EVENT_TEMPLATES` = 7 events, one per `FEATURED_CATEGORIES`, 3–8 `EventOutcomeSpec`s with independent odds (Politics 3, Sports 6, Economy 4, Crypto 5, Pop Culture 5, Tech 5, World 4); `_assert_featured_categories_match_canonical()` guards full coverage. Test: `test_seed_events_fill_featured_categories` (each featured tab present + ≥2 items). |
| **SC2** open + partially-resolved + resolved + void, each with non-flat odds history | DEMO-02 | ✅ | States driven via `EventService.resolve_event` / `void_event` / single-child `SettlementService.resolve_market` (partial) / untouched (open). Test: `test_seed_events_cover_all_four_states` asserts all 4 derived states present; `test_seed_events_non_flat_odds_history` asserts an event child's `OddsSnapshot` series is non-flat (>1 distinct value, ≥2 points). |
| **SC3** every category tab filled above a minimum; featured allow-list pinned + drift-insulated | DEMO-03 | ✅ | `FEATURED_CATEGORIES` pinned (hardcoded) + coherence guard vs `POLYMARKET_CATEGORIES`; standalone templates retagged onto the canonical 7 (no stray tabs). Test (hermetic): `test_seed_events_fill_featured_categories` — `list_categories` ⊇ featured + `list_catalog(category=…)` ≥ `MIN_ITEMS_PER_FEATURED_CATEGORY` (2) for every featured category. |
| **SC4** `demo-reset` idempotent; integrity green after seed AND reset | DEMO-04 | ✅ | `market_groups` added to `_RESET_TABLES` (the missing-truncation idempotency fix); `verify_integrity()` surfaces `_reconcile_async` (drift) in the CLI for both paths. Tests: `test_reset_clears_market_groups_and_reseeds` (re-seed of deterministic slugs succeeds post-reset) + every event test asserts reconcile drift == baseline (green); `test_main_reset_wipes_and_repopulates`. |

## Requirement → proof (DEMO-01..04)

- **DEMO-01** ✅ — `seed_events` creates one marquee house event per featured category via
  `EventService.create_house_event`; 3–8 independent binary children (per-outcome YES prices never
  sum to 100% — the framing LOCK). Proof: `test_seed_events_fill_featured_categories`.
- **DEMO-02** ✅ — all four event states produced + non-flat per-outcome odds (reuses
  `seed_odds_history` over event children). Proof: `test_seed_events_cover_all_four_states`,
  `test_seed_events_non_flat_odds_history`.
- **DEMO-03** ✅ — pinned, drift-guarded featured allow-list; every featured tab ≥2 items. Proof:
  `test_seed_events_fill_featured_categories` (hermetic) + `_assert_featured_categories_match_canonical`.
- **DEMO-04** ✅ — `--reset` clears `market_groups` → idempotent re-seed; reconcile green after seed
  and reset. Proof: `test_reset_clears_market_groups_and_reseeds`, baseline-relative reconcile in
  every event test, CLI `integrity: …drift=N` line.

## Integration acceptance (the milestone intent)

The seed exercises the full v1.2 stack end-to-end through the merged service layer — Phase 13 model
(`market_groups` + children), Phase 15 settlement (`resolve_event`/`void_event`/`resolve_market`),
Phase 16 catalog API (`list_catalog`/`list_categories` assertions), and the Phase 17 UI's data
contract (categories + events) — with the spike-004 double-entry ledger reconciling to **zero added
drift** on every path. No backend domain code changed; no new dependencies.

## Money / safety invariants (re-confirmed by 2 independent reviews — see 18-REVIEW.md)

Money discipline · 23505 session-per-call · resolve_event CR-01 · reset CASCADE correctness ·
integrity-green · no wallet overdraw — all HOLD. Review verdict: CLEAN.

**Verification result: PASSED.**
