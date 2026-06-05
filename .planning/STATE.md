---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: Credible Catalog
status: executing
last_updated: "2026-06-05T13:07:37Z"
last_activity: 2026-06-05 -- Executed 14-04 (poll_polymarket_events curation loop + distinct EVENTS_LOCK_KEY + beat swap top25@30s->events@300s; 10/10 test_tasks.py unit green per-module) — Phase 14 plans 4/4 done
progress:
  total_phases: 6
  completed_phases: 1
  total_plans: 6
  completed_plans: 6
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-04)
Roadmap: .planning/ROADMAP.md — v1.2 Credible Catalog = Phases 13-18 (Model → Sync → Settlement → API → UI → Seed).

**Core value:** El operador puede ofrecer un catálogo creíble de mercados de predicción (mezcla de Polymarket y house) con liquidación correcta y CRM para gestionar usuarios, todo bajo su marca — sin construir ni operar la pieza técnica.
**Current focus:** Phase 14 (Curated Per-Category Gamma Sync) — ALL 4 PLANS DONE (awaiting verify + PR). Wave 1: 14-01 ✅ (Gamma /events data-contract: parsers + POLYMARKET_CATEGORIES + curation settings) and 14-02 ✅ (GammaClient.fetch_events — ranked /events, 500 cap, per-endpoint rate docstring). Wave 2: 14-03 ✅ (adapter: _upsert_one_market extraction + sync_events + _upsert_market_group — first writer of market_groups; CAT-04/EVT-07/CAT-06). Wave 3: 14-04 ✅ (poll_polymarket_events curation loop — dedup→floor→top-N→commit-per-category keep-last-good + distinct EVENTS_LOCK_KEY WR-05 lock + beat swap top25@30s→events@300s; CAT-01/02/03/05). ⚠️ Deploy: redbeat persists the schedule in Redis → restart the beat process on deploy for the swap to take effect (Pitfall 5). Next: Phase 14 verify/code-review + 1 PR (gsd/phase-14-curated-per-category-gamma-sync), then Phase 15 (Event Settlement). (Phase 13 MERGED PR #25; backend-CI-green PR #26 awaiting Pol's merge.)

## Current Position

Phase: 14 (Curated Per-Category Gamma Sync) — 🔨 ALL PLANS DONE (verify/PR pending)
Plan: 4 of 4 complete (14-01 ✅ parsers+config · 14-02 ✅ fetch_events · 14-03 ✅ adapter sync_events + market_groups writer · 14-04 ✅ poll_polymarket_events curation loop + beat swap)
Status: Executing — Phase 14 plans complete; next is phase verify/code-review + 1 PR, then Phase 15
Last activity: 2026-06-05 -- Executed 14-04 (poll_polymarket_events curation loop + distinct EVENTS_LOCK_KEY + beat swap top25@30s->events@300s; 10/10 test_tasks.py unit green per-module)

Progress: [██████████] 100%

> Note (Windows worktree ONLY — not a code issue): on this Windows worktree the full `uv run pytest` flakes (testcontainers connection contention across unrelated modules) AND `ruff check`/`format` results flip-flop (the worktree file set flickers 148↔202 between identical runs). **Linux CI runs the full suite (`pytest tests/ -x`) + ruff + mypy GREEN** (PR #26 `backend` job, 1m45s). Diagnose backend on Linux CI, not the Windows worktree. See [[xprediction-backend-fullsuite-testcontainers-flake]].

## Milestones Shipped

See [`MILESTONES.md`](MILESTONES.md) for full summaries.

- ✅ **v1.0 MVP** — Phases 1-12 (shipped 2026-06-04) — archived to `milestones/v1.0-{ROADMAP,REQUIREMENTS,MILESTONE-AUDIT}.md` + `milestones/v1.0-phases/`.
- ✅ **v1.1 Demo Polish** — Fases A-E via PRs #19/#22/#23/#24 (shipped 2026-06-04) — plan-of-record `milestones/v1.1-MILESTONE-CONTEXT.md`.

## Deferred Items

Acknowledged and carried forward at the v1.0/v1.1 close (2026-06-04). Source: `gsd-sdk query audit-open` + Phase 11 gating note.

| Category | Item | Status | Notes |
|----------|------|--------|-------|
| human-UAT | Phase 12 `12-HUMAN-UAT.md` | 3 scenarios open | PM-accepted human-verify items from the v1.0 closure phase. |
| verification | Phases 03 / 04 / 05 | 3 VERIFICATION.md missing | Flagged by the 2026-06-02 v1.0 audit; backends tested + shipped, formal VERIFICATION.md never written. |
| legal (gating) | Spanish counsel review of ToS + token policy | Open — **not deferrable** | Must complete **before any live demo to a real operator**. Carried from Phase 11. |

## Accumulated Context

Full decision log lives in PROJECT.md (Key Decisions); per-phase execution detail in the archived `milestones/v1.0-phases/*/*-SUMMARY.md`.

**Open, affects future work:**

- **Legal gate (above):** Spanish legal counsel must review ToS + token policy before any operator-facing demo. Gating, not deferrable.
- **Future-milestone seams already in place** (de-risks later milestones): `tenant_id` ghost columns + feature-flags table (multi-tenancy), Stripe stub interface `WalletService.recharge(payment_provider=...)` (real money). Both remain deferred (post-v1.2).
- **v1.2 multi-outcome = event-of-binaries** (decided 2026-06-04): each outcome is an independent binary YES/NO market grouped under an "event" — reuses the existing binary model + settlement, so the binary-only DB `CHECK` does NOT need to change. Coherent with mirroring Polymarket's native event structure.

## Session Continuity

Last session: 2026-06-05T13:07:37Z
Stopped at: Completed 14-04-PLAN.md — poll_polymarket_events curation loop (dedup→floor→top-N→commit-per-category keep-last-good) + distinct EVENTS_LOCK_KEY WR-05 lock + beat swap top25@30s→events@300s; 10/10 test_tasks.py unit green per-module. Phase 14 plans 4/4 done — ready for phase verify/code-review + 1 PR.
Resume file: None

## Performance Metrics

| Phase | Plan | Duration | Notes |
|-------|------|----------|-------|
| Phase 13 P13-01 | 8min | 2 tasks | 5 files |
| Phase 13 P13-02 | ~10min | 2 tasks | 2 files (test_migration_0011.py +349, test_models.py +137) |
| Phase 14 P14-01 | 14min | 3 tasks | 4 files |
| Phase 14 P14-02 | 3min | 2 tasks (1 TDD) | 2 files (client.py, test_client.py) |
| Phase 14 P14-03 | ~16min | 3 tasks | 2 files (adapter.py, test_adapter.py) |
| Phase 14 P14-04 | ~5min | 3 tasks (1 TDD) | 3 files (tasks.py, celery_app.py, test_tasks.py) |

## Decisions

- [Phase 14]: GammaEventMarket subclasses GammaMarket — inherits spike-002 validators + _derive_status verbatim, adds only group_item_title
- [Phase 14]: Event-level Gamma /events volume24hr/volume are FLOAT -> Decimal via properties; stringified-JSON list validator stays only on GammaMarket (Pitfall 1)
- [Phase 14]: fetch_events hard-caps limit via min(limit, 500) at the client layer (CAT-05/T-14-06) — caller can never flood Gamma; offset exposed for the 14-04 short-page loop
- [Phase 14]: client.py rate-limit docstring corrected (300=/markets, 500=/events) not deleted — preserves the accurate /markets fact; the plan's grep-for-0 acceptance check is a false positive (the figure lives in a docstring string, not a # comment line)
- [Phase 14]: sync_events is the first writer of market_groups — 1 group + N children for multi-outcome events; len==1 stays standalone with NO group row (EVT-07)
- [Phase 14]: _upsert_one_market extracted from sync_top25 (shared idempotent upsert); +category/group_id/group_item_title on INSERT and ON CONFLICT; sync_top25 delegates with nulls (back-compat byte-equivalent)
- [Phase 14]: MarketGroup slug collision across different events retried once with a uuid6 suffix inside a SAVEPOINT (begin_nested) so one clash can't abort siblings (Pitfall 6)
- [Phase 14]: _run_poll_events mirrors _run_poll_sync verbatim, generalized to a per-category loop; commit-per-category with a per-category try/except keep-last-good (CAT-05) so one poisoned category never aborts the cycle or blanks the catalog (sync only upserts)
- [Phase 14]: cross-cycle event-id dedup via a loop-level seen_event_ids set applied BEFORE the volume24hr floor — gives first-by-priority for free AND prevents Polymarket cross-category volume double-count inflating a borderline event over the floor (CAT-02/Pitfall 4)
- [Phase 14]: distinct EVENTS_LOCK_KEY (xpredict:poll:events:lock) + dedicated acquire/release helpers reusing _RELEASE_LOCK_LUA (WR-05), TTL=POLYMARKET_EVENTS_LOCK_TTL_SECONDS (280s < 300s tick); legacy poll-lock helpers kept byte-stable (their unit tests assert the exact call shape)
- [Phase 14]: beat swap is an in-place literal edit (drop poll-polymarket-top25@30s, add poll-polymarket-events@300s), NOT a dict reassignment; poll_polymarket_top25 task kept importable+registered (back-compat). ⚠️ redbeat persists the schedule in Redis → restart beat on deploy (Pitfall 5)
