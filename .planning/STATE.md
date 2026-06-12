---
gsd_state_version: 1.0
milestone: v1.4
milestone_name: Premium Experience
status: v1.4 shipped — awaiting next milestone
last_updated: "2026-06-11"
last_activity: 2026-06-11 — Completed quick task 260611-lcr: One-click demo access (/auth/demo-login + demo button)
progress:
  total_phases: 1
  completed_phases: 1
  total_plans: 1
  completed_plans: 1
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-04)
Roadmap: .planning/ROADMAP.md — milestone-grouped view (v1.0 → v1.4).

**Core value:** El operador puede ofrecer un catálogo creíble de mercados de predicción (mezcla de Polymarket y house) con liquidación correcta y CRM para gestionar usuarios, todo bajo su marca **XPrediction** — sin construir ni operar la pieza técnica.

**Current focus:** **No active milestone.** Everything started is shipped to `main`. v1.0, v1.1, v1.2, v1.3 and v1.4 are all merged; the planning record was reconciled on 2026-06-06 to match git (the docs had drifted — STATE/HANDOFF still said "v1.2, awaiting v1.3"). Next: define the next milestone — run `/gsd-new-milestone`.

## Current Position

Phase: — (no phase in flight; `.planning/phases/` is empty)
Plan: —
Status: v1.4 Premium Experience shipped → awaiting next milestone definition
Last activity: 2026-06-11 — Completed quick task 260611-u0q: SlotsLaunch Casino (demo) section (catalog proxy + /casino page)

> **Truth-source rule:** verify live state from git (`git log`, `origin/main`, `gh pr ...`), not these docs alone — they can drift. As of this reconciliation: `origin/main` @ `2b2fca8`, single alembic head `0011_livebets_bridge`, **0 open PRs, 0 phase branches in flight.**

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260611-lcr | One-click demo access: /auth/demo-login + demo button | 2026-06-11 | bde21b1 | [260611-lcr-one-click-demo-access-auth-demo-login-de](./quick/260611-lcr-one-click-demo-access-auth-demo-login-de/) |
| 260611-u0q | SlotsLaunch Casino (demo): catalog proxy + /casino page + fullscreen launcher | 2026-06-11 | 222c8ee | [260611-u0q-integrate-slotslaunch-demo-slots-as-casi](./quick/260611-u0q-integrate-slotslaunch-demo-slots-as-casi/) |

## Milestones Shipped

See [`MILESTONES.md`](MILESTONES.md) for full summaries. All on `main`.

- ✅ **v1.0 MVP** — Phases 1-12 (shipped 2026-06-04) — archived to `milestones/v1.0-*` + `milestones/v1.0-phases/`.
- ✅ **v1.1 Demo Polish** — Fases A-E via PRs #19/#22/#23/#24 (shipped 2026-06-04) — plan-of-record `milestones/v1.1-MILESTONE-CONTEXT.md`.
- ✅ **v1.2 Credible Catalog** — Phases 13-18 via PRs #25/#28/#29/#30/#31/#32 (shipped 2026-06-06) — archived to `milestones/v1.2-*` + `milestones/v1.2-phases/`. **Tag `v1.2`** @ shipped.
- ✅ **v1.3 Live-Bets demo** — Fases LB-A/B/C, off-grid, merged via `171aee5` (shipped 2026-06-06) — `milestones/v1.3-MILESTONE-CONTEXT.md` + `milestones/v1.3-MILESTONE-AUDIT.md` + `milestones/v1.3-phases/`. **Tag `v1.3`** @ `171aee5`.
- ✅ **v1.4 Premium Experience** — Phase 19 via PR #33, merged `2b2fca8` (shipped 2026-06-06) — `milestones/v1.4-MILESTONE-CONTEXT.md` + `milestones/v1.4-MILESTONE-AUDIT.md` + `milestones/v1.4-phases/`. **Tag `v1.4`** @ `2b2fca8`.

## Deferred Items

Carried forward across milestones. Still open after the v1.4 close.

| Category | Item | Status | Notes |
|----------|------|--------|-------|
| legal (gating) | Spanish counsel review of ToS + token policy | Open — **NOT deferrable** | Must complete **before any live demo to a real operator**. Carried from Phase 11. The single hard gate. |
| human-UAT | Phase 12 `12-HUMAN-UAT.md` | 3 scenarios open | PM-accepted human-verify items from the v1.0 closure phase. |
| human-UAT | Phase 14 `14-HUMAN-UAT.md` | 2 scenarios open | Live-runtime checks (redbeat schedule reload on deploy; Gamma `tag_id` allow-list drift re-verify). Only closeable on a real deploy. |
| verification | Phases 03 / 04 / 05 | 3 VERIFICATION.md missing | Flagged by the 2026-06-02 v1.0 audit; backends tested + shipped, formal VERIFICATION.md never written. |
| backend (Phase 17 follow-up) | Dedicated admin event-list endpoint + editable `resolution_criteria` on `UpdateEventRequest` | Deferred | Phase 17 UI uses the public catalog (house-filtered) for the admin list; criteria not editable post-create. |
| frontend integration (v1.4 / Phase 19) | Point frontend env at the definitive backend; set `tenant_config.brand_name = "XPrediction"`; drop official logo PNG at `frontend/public/brand/xprediction-logo.png` | Open — handoff to Pol | Phase 19 is frontend-complete + backend-integration-ready; see `milestones/v1.4-phases/phase-19-premium-experience/HANDOFF.md`. Logo falls back to a faithful vector mark until the PNG is dropped — nothing broken. |

## Accumulated Context

Full decision log lives in PROJECT.md (Key Decisions); per-phase execution detail in the archived `milestones/v{X.Y}-phases/*/*-SUMMARY.md`.

**Open, affects future work:**

- **Legal gate (above):** Spanish legal counsel must review ToS + token policy before any operator-facing demo. Gating, not deferrable.
- **Future-milestone seams already in place** (de-risks later milestones): `tenant_id` ghost columns + feature-flags table (multi-tenancy), Stripe stub interface `WalletService.recharge(payment_provider=...)` (real money). Both remain deferred.
- **v1.2 multi-outcome = event-of-binaries** (decided 2026-06-04): each outcome is an independent binary YES/NO market grouped under an "event" — reuses the existing binary model + settlement, so the binary-only DB `CHECK` does NOT change. The per-outcome framing LOCK (independent YES bars, NEVER sum-to-100) is the gating visual invariant, preserved through v1.4.
- **v1.3 Live-Bets is demo-only + additive:** unified XPredict wallet mirrors live-bets money event-driven + idempotent; real money/PSP/OAuth/production webhook hardening explicitly out of scope.
- **v1.4 brand:** visible brand = **"XPrediction"** everywhere; technical names stay `XPredict/xpredict` (cookie `xpredict_session`, env vars, repo). White-label runtime branding pipeline preserved (real operator names still override).

## Session Continuity

Last session: 2026-06-06
Stopped at: **Planning reconciliation.** Brought `.planning/` in line with git after v1.3 (Live-Bets) and v1.4 (Phase 19 Premium Experience) had merged to `main` while STATE/HANDOFF still described v1.2. Actions: archived `LB-A/B/C` → `milestones/v1.3-phases/` and `phase-19-premium-experience` → `milestones/v1.4-phases/` (so `.planning/phases/` is empty — no work in flight); created v1.3 + v1.4 milestone audits; rewrote ROADMAP/MILESTONES/HANDOFF/STATE; tags `v1.3` (`171aee5`) + `v1.4` (`2b2fca8`). Landed on branch `chore/planning-reconcile-v1.3-v1.4` → PR for Pol.
Resume file: None

## Decisions (recent)

- [Reconciliation 2026-06-06]: Phase 19 (Premium Experience) classified as its own milestone **v1.4** (distinct theme, posterior to v1.3 Live-Bets), not folded into v1.3.
- [Phase 18]: Seed/Demo harness for multi-outcome — extends `bin/seed_demo.py` through the MERGED service layer (zero new domain code); 4 event states; `market_groups` added to `_RESET_TABLES` (DEMO-04 idempotency fix); reconcile green after seed AND reset.
- [Phase 17]: First v1.2 FRONTEND phase against the merged Phase-16 API (zero backend changes). Per-outcome framing LOCK (independent YES bars, NEVER sum-to-100) enforced by tests; fixed a real duplicate-socket leak.
- [v1.3 LB-A]: Live-bets ledger mirror is event-driven + idempotent by `bet_id`, server-verified via `GET /v2/bets/{id}`, per-player ownership (IDOR-safe); additive migration only (`livebets_escrow` account + `livebets_bets` table). 23505 session-per-call discipline preserved.
- [v1.4 / Phase 19]: Frontend-only "Obsidian & Spark" dark-first redesign + platform-first landing + app behind auth + premium admin; white-label runtime branding + money-as-strings + framing-LOCK + single-live-socket invariants all preserved (5-lens adversarial review, no HIGH).

> Full per-phase decision detail is preserved in the archived `milestones/v{X.Y}-phases/*/*-SUMMARY.md` and the v1.2 decisions block in `milestones/v1.2-MILESTONE-AUDIT.md`.

## Operator Next Steps

- Start the next milestone with `/gsd-new-milestone` (candidates: multi-tenancy runtime, real money Stripe/KYC, full Polymarket catalog, live-bets productionization).
- **Before any live operator demo:** close the Spanish legal review gate (ToS + token policy).
