---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: Credible Catalog
status: executing
last_updated: "2026-06-05T17:02:39.741Z"
last_activity: 2026-06-05
progress:
  total_phases: 6
  completed_phases: 2
  total_plans: 9
  completed_plans: 7
  percent: 33
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-04)
Roadmap: .planning/ROADMAP.md — v1.2 Credible Catalog = Phases 13-18 (Model → Sync → Settlement → API → UI → Seed).

**Core value:** El operador puede ofrecer un catálogo creíble de mercados de predicción (mezcla de Polymarket y house) con liquidación correcta y CRM para gestionar usuarios, todo bajo su marca — sin construir ni operar la pieza técnica.
**Current focus:** Phase 15 — Event Settlement (House Resolve/Void + Mirrored Verify)

## Current Position

Phase: 15 (Event Settlement (House Resolve/Void + Mirrored Verify)) — EXECUTING
Plan: 2 of 3
Status: Ready to execute
Last activity: 2026-06-05

Progress: [████████░░] 78%

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

Last session: 2026-06-05T17:02:39.735Z
Stopped at: Completed 15-01-PLAN.md (Wave 1 — EVT-06 derive_event_status pure projection + 8 unit tests GREEN, no Docker)
Resume file: None

## Performance Metrics

| Phase | Plan | Duration | Notes |
|-------|------|----------|-------|
| Phase 13 P13-01 | 8min | 2 tasks | 5 files |
| Phase 13 P13-02 | ~10min | 2 tasks | 2 files (test_migration_0011.py +349, test_models.py +137) |
| Phase 15 P01 | 3min | 2 tasks | 2 files |

## Decisions

- [Phase 15]: EVT-06: event status is a derived read-time projection (derive_event_status pure free function over ChildStatus); no stored status/winning_outcome column on market_groups, no migration
- [Phase 15]: derive_event_status + ChildStatus live module-level in backend/app/settlement/event_service.py (Wave 1 pure layer); Wave 2 EventService resolve/void/reverse class extends the same module
