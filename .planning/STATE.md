---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: Credible Catalog
status: phase_complete
last_updated: 2026-06-06T00:00:00.000Z
last_activity: 2026-06-06
progress:
  total_phases: 6
  completed_phases: 5
  total_plans: 19
  completed_plans: 19
  percent: 83
stopped_at: Phase 17 MERGE READY — PR #31, CI 7/7 green; Phase 18 (Seed/Demo) next
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-04)
Roadmap: .planning/ROADMAP.md — v1.2 Credible Catalog = Phases 13-18 (Model → Sync → Settlement → API → UI → Seed).

**Core value:** El operador puede ofrecer un catálogo creíble de mercados de predicción (mezcla de Polymarket y house) con liquidación correcta y CRM para gestionar usuarios, todo bajo su marca — sin construir ni operar la pieza técnica.
**Current focus:** Phase 18 — seed/demo harness for multi-outcome + categories (Phase 17 frontend is MERGE READY)

## Current Position

Phase: 18
Plan: Not started
Status: Phase 17 (UI) MERGE READY — PR [#31](https://github.com/polito101/xpredict/pull/31) OPEN, CI 7/7 green, MERGEABLE, 0 drift, awaiting Pol's review/merge. Phase 18 (Seed/Demo) ready to plan.
Last activity: 2026-06-06

Progress: [████████░░] 83%

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

Last session: 2026-06-06
Stopped at: Phase 17 (Catalog Browse UI, Event Detail & Admin Event Ops) executed end-to-end autonomously — 5 plans (data layer → browse → event detail → admin event ops → brand sweep), ~30 frontend files, 188 vitest green + tsc/eslint/`next build --webpack` clean; 2 independent code reviews (framing LOCK / security / a11y / BRW-06 = PASS, 1 HIGH + 2 MED + 4 LOW all fixed); verification PASSED. PR [#31](https://github.com/polito101/xpredict/pull/31) OPEN, CI 7/7 green, MERGEABLE, 0 drift → MERGE READY (awaiting Pol). Next: Phase 18 (Seed/Demo) after #31 merges.
Resume file: None

## Performance Metrics

| Phase | Plan | Duration | Notes |
|-------|------|----------|-------|
| Phase 13 P13-01 | 8min | 2 tasks | 5 files |
| Phase 13 P13-02 | ~10min | 2 tasks | 2 files (test_migration_0011.py +349, test_models.py +137) |
| Phase 15 P01 | 3min | 2 tasks | 2 files |
| Phase 15 P02 | 9min | 2 tasks | 2 files |
| Phase 15 P03 | 15min | 3 tasks | 3 files (event_service.py +140, test_event_service.py +256 reverse, test_event_mirrored.py +482 new) |
| Phase 16 P01 | ~12min | 2 tasks | 3 files (catalog scaffold: __init__.py, conftest.py, _factories.py +457) |

## Decisions

- [Phase 15]: EVT-06: event status is a derived read-time projection (derive_event_status pure free function over ChildStatus); no stored status/winning_outcome column on market_groups, no migration
- [Phase 15]: derive_event_status + ChildStatus live module-level in backend/app/settlement/event_service.py (Wave 1 pure layer); Wave 2 EventService resolve/void/reverse class extends the same module
- [Phase 15]: Phase-15 event resolve/void = loop the UNCHANGED SettlementService per child on a FRESH _get_session_maker() session (Option A); never two self-committing settles in one with/begin() (the 23505 dangling-tx landmine). Idempotency/locks/payouts/per-child audit all inherited.
- [Phase 15]: EventService integration tests seed LEDGER-BACKED wallets (INSERT at 0 + WalletService.recharge) so the literal spike-004 _reconcile_async drift_count==0 gate is faithful; the older raw-balance test shortcut leaves a phantom non-ledger-backed opening balance the reconciler reports as drift.
- [Phase 15]: EventService.reverse_event (EVA-05) loops the UNCHANGED SettlementService.reverse_settlement per already-settled child on a FRESH session, NO winning_outcome_id (finds SETTLED bets by status). Per-child sessions do double duty: 23505-safe AND isolate the CHECK(balance>=0) floor (a winner who spent winnings makes THAT child roll back alone, siblings stay reversed; full reverse reopens all → event derives "open"). Reverse is restore+audit ONLY; re-resolve-after-reverse is a deferred Pitfall-6 gap (settle:{bet_id}:{leg} collides on 23505), flagged in code, no test.
- [Phase 15]: EVA-06 is VERIFY-ONLY — backend/app/integrations/polymarket/tasks.py has NO diff. test_event_mirrored.py drives the UNCHANGED _run_detect_resolutions over a source=POLYMARKET market_group's children via its session_override/redis_override seam (settle with zero new code) + asserts reverse_event rejects mirrored. A grace-PRIMER market (uma_resolved_at NULL, committed first) grace-starts+commits in the detect loop to clear the candidate-SELECT read tx so each child's resolve_market opens its own begin() on a real session_override (a real session forbids begin() while a read tx is open — reproduces a real mixed-stage 60s tick); AsyncMock detect-lock (in-repo fakeredis lacks Lua eval).
- [Phase 15]: Phase 15 event-settlement layer COMPLETE — resolve + void + reverse + derived status + mirrored verify, all with spike-004 drift_count==0 on every path; all 3 EventService mutations reject source=POLYMARKET groups (mirrored settles ONLY via the unchanged UMA detect path).
- [Phase 16]: Wave-0 catalog test scaffold (16-01) — tests/catalog/ package; conftest inherits the parent engine/async_session fixtures and adds only the api ASGITransport client + autouse testcontainer/override fixtures. _factories.py exposes make_market, make_event (MarketGroup + N binary YES/NO children), place_bet_on_child, resolve_child + per-state drivers (open/partial/resolved/void), and _Admin/admin_override/seed_admin. place_bet_on_child funds a LEDGER-BACKED wallet via WalletService.recharge on a FRESH committed session then writes the Bet on the caller session (Pitfall 5: recharge owns its own begin()+commit, can't run on the rolled-back async_session fixture). Per-state drivers mutate child status + winning_outcome_id directly (the plan's allowed non-financial state setup) consistent with derive_event_status; all money/odds are Decimal; children are binary YES/NO only (trg_binary_outcomes_only never trips).
- [Phase 17]: First v1.2 FRONTEND phase — built entirely against the merged Phase-16 API (zero backend changes). The per-outcome framing LOCK (each outcome an independent YES bar, NEVER sum-to-100) is the gating visual invariant; tests assert >100% sums to forbid normalization. Catalog browse upgraded the homepage `/` (curated `/catalog` superset of `/markets`); event detail reuses `OrderEntryForm`/`PriceHistorySection`/`MarketDetailLiveOdds` per selected child (fetched via `fetchMarket(child_slug)` for the real YES+NO); the live-WS cap is structural (single `key={child.id}` panel remount → one socket). Admin event dialogs use the backend's server two-step (`confirm:false` preview → `confirm:true` execute). Admin events list reads the public catalog filtered to house events (no admin list endpoint — deferred). Caught + fixed a real duplicate-socket leak (per-element key on a conditional). 36 new tests.
