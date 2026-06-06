# Roadmap: XPredict

> Compact milestone-grouped view. Full per-milestone detail is archived under
> [`milestones/`](milestones/) (`v{X.Y}-ROADMAP.md`); phase execution history in
> [`milestones/v1.0-phases/`](milestones/v1.0-phases/). See [`MILESTONES.md`](MILESTONES.md) for shipped summaries.

## Milestones

- ✅ **v1.0 MVP** — Phases 1-12 (shipped 2026-06-04) — production-grade play-money prediction market, end-to-end.
- ✅ **v1.1 Demo Polish** — Fases A-E (shipped 2026-06-04) — brand-aware design system, seed/demo harness, player & operator polish, demo QA.
- ✅ **v1.2 Credible Catalog** — Phases 13-18 (shipped 2026-06-06) — multi-outcome events (event-of-binaries) + curated per-category catalog + browse + admin event ops + demo seed.
- ✅ **v1.3 Live-Bets demo** — Fases LB-A/B/C (shipped 2026-06-06, off-grid) — embed live-bets multi-player betting inside XPredict as operator: unified XPredict wallet, embedded `<live-bets-table>` widget, event-driven idempotent ledger mirror. Demo-only, additive.

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-12) — SHIPPED 2026-06-04</summary>

- [x] **Phase 1: Project Scaffold, Infra & Cross-Cutting Foundations** — Docker stack, FastAPI + Next.js, Postgres 16 + Redis, Alembic, money-column standards, `tenant_id` ghost column, audit-log trigger, Sentry, gitleaks CI.
- [x] **Phase 2: Auth & Identity** — Player + admin auth (Argon2id / fastapi-users), email verification, password reset, refresh-token rotation, rate-limiting.
- [x] **Phase 3: Wallet & Double-Entry Ledger** — Append-only double-entry ledger, `NUMERIC(18,4)`/`Decimal`, `FOR UPDATE` + idempotency, non-negative + non-transferable constraints.
- [x] **Phase 4: Markets Domain & HouseAdapter** — `MarketSource` Protocol, house markets CRUD backend, binary YES/NO model.
- [x] **Phase 5: Bets, Settlement & First End-to-End Demo (House Markets Only)** — ACID bet placement, `SettlementService`, idempotent settlement, audit trail; first end-to-end demoable happy path.
- [x] **Phase 6: Polymarket Sync (Catalog Replication)** — Gamma API polling (Celery Beat + RedBeat lock), top-25 mirror, odds snapshots.
- [x] **Phase 7: Polymarket Auto-Resolution & Admin Override** — UMA confirmed-resolved auto-settle with grace window, admin force-settle override.
- [x] **Phase 8: Admin CRM (User Management & Audit Log Viewer)** — Paginated users, detail, ban/unban, CSV export, immutable audit log viewer.
- [x] **Phase 9: User App UX Polish (Market Detail & Real-Time)** — Market detail, price-history chart, WebSocket real-time prices.
- [x] **Phase 10: Admin KPI Dashboard & Configurable Branding** — KPI dashboard (Recharts), audit log filters, single-row TenantConfig branding.
- [x] **Phase 11: Hardening & Operator-Demo Gate** — "Looks Done But Isnt" hardening checklist, demo gate.
- [x] **Phase 12: Admin Market Operations UI & Player Resolution Display** — v1.0 closure: admin markets list/create/edit/close + resolve/reverse/force-settle dialogs, per-market stake limits (BET-06), player resolution display (STL-06).

</details>

<details>
<summary>✅ v1.1 Demo Polish (Fases A-E) — SHIPPED 2026-06-04</summary>

> Executed off the formal phase grid in parallel git worktrees and landed via PRs (not numbered phases).
> Plan-of-record: [`milestones/v1.1-MILESTONE-CONTEXT.md`](milestones/v1.1-MILESTONE-CONTEXT.md).

- [x] **Fase A: Design system brand-aware** — propagate `--brand-*` to primitives + brand typography (`next/font`) + motion tokens (`framer-motion`). *(PR #22)*
- [x] **Fase B: Seed & demo harness** — realistic seed (users, house + mirrored markets, open & resolved, bets with P&L, odds history) + `demo-reset`. *(PR #19)*
- [x] **Fase C: Player polish** — header-nav, microinteractions, weighted success states, non-silent errors + loading states, responsive. *(PR #22)*
- [x] **Fase D: Operator polish** — admin loading skeletons + responsive tables, panel completeness. *(PR #23)*
- [x] **Fase E: Demo QA / guion** — step-by-step sales script + E2E happy-path QA checklist. *(PR #24)*

</details>

<details>
<summary>✅ v1.2 Credible Catalog (Phases 13-18) — SHIPPED 2026-06-06</summary>

> Multi-outcome events modeled as groups of independent binary markets (event-of-binaries) + a credible per-category browse. Purely additive schema. Full detail archived in [`milestones/v1.2-ROADMAP.md`](milestones/v1.2-ROADMAP.md); audit in [`milestones/v1.2-MILESTONE-AUDIT.md`](milestones/v1.2-MILESTONE-AUDIT.md) (29/29 reqs, verdict tech_debt).

- [x] **Phase 13: Multi-outcome Model & Catalog Indexes** (2/2) — `market_groups` + nullable `Market.group_id`/`group_item_title` + pg_trgm + 6 catalog indexes (migration 0011); zero behavior change. — 2026-06-05
- [x] **Phase 14: Curated Per-Category Gamma Sync** (4/4) — Gamma `/events` per-category curated ingestion replaces the top-25 poll; keep-last-good; first writer of `market_groups`. — 2026-06-05 *(2 live human-UAT checks deferred)*
- [x] **Phase 15: Event Settlement (Resolve/Void/Reverse + Mirrored Verify)** (3/3) — `EventService` loops the unchanged `SettlementService` per child on fresh sessions; derived event status. — 2026-06-05
- [x] **Phase 16: Catalog & Event API + House Event CRUD** (5/5) — browse/search/category/event reads + house-event CRUD + resolve/void/reverse endpoints, two-step confirm. — 2026-06-05
- [x] **Phase 17: Catalog Browse UI, Event Detail & Admin Event Ops** (5/5) — per-outcome independent rows (never sum-to-100) + admin event dialogs; white-label. — 2026-06-06
- [x] **Phase 18: Seed/Demo Harness for Multi-outcome + Categories** (1/1) — marquee multi-outcome event per category across all 4 states; idempotent reset + integrity check. — 2026-06-06

</details>

<details>
<summary>✅ v1.3 Live-Bets demo (Fases LB-A/B/C) — SHIPPED 2026-06-06 (off-grid)</summary>

> Off the formal phase grid (like v1.1): isolated worktree (`xpredict-livebets`, branch `gsd/livebets-demo`), landed via direct merge; `.planning/` reconciled here. Plan-of-record: [`milestones/v1.3-MILESTONE-CONTEXT.md`](milestones/v1.3-MILESTONE-CONTEXT.md). Design contract: [`live-bets-integration-design`](../docs/superpowers/specs/2026-06-05-live-bets-integration-design.md). Runbook: [`../docs/superpowers/DEMO-RUNBOOK-live-bets.md`](../docs/superpowers/DEMO-RUNBOOK-live-bets.md).

- [x] **Fase LB-A: Backend bridge** — `app/integrations/livebets/` (httpx client + `LiveBetsBridge` + router) + additive migration (`livebets_escrow` system account + `livebets_bets` mirror table) + config + tests. Event-driven idempotent ledger mirror (debit on `bet-placed`, credit on settle), server-verified via `GET /v2/bets/{id}`; per-player ownership (IDOR-safe).
- [x] **Fase LB-B: Frontend surface** — `/live` route embedding `<live-bets-table>` in XPredict chrome + wallet; DOM-event wiring to backend; "Live" nav entry; HttpOnly cookie via Server Actions; component tests.
- [x] **Fase LB-C: Demo harness** — isolated live-bets instance (`:8002`, CORS), full-scope operator key, clips + orchestrator (live rounds), env wiring + runbook. E2E proven: bet from `/live` → XPredict wallet moves. Real contract drift vs the v3 guide fixed (`GET /tables`, `BetView.id/selection`, `/v2/sessions` Idempotency-Key).

</details>

## Progress

| Phase | Milestone | Plans | Status | Completed |
|-------|-----------|-------|--------|-----------|
| 1-12. v1.0 MVP | v1.0 | 44/44 | ✅ Complete | 2026-06-04 |
| A-E. Demo Polish | v1.1 | — | ✅ Complete | 2026-06-04 |
| 13. Multi-outcome Model & Catalog Indexes | v1.2 | 2/2 | ✅ Complete | 2026-06-05 |
| 14. Curated Per-Category Gamma Sync | v1.2 | 4/4 | ✅ Complete | 2026-06-05 |
| 15. Event Settlement (Resolve/Void/Reverse + Mirrored Verify) | v1.2 | 3/3 | ✅ Complete | 2026-06-05 |
| 16. Catalog & Event API + House Event CRUD | v1.2 | 5/5 | ✅ Complete | 2026-06-05 |
| 17. Catalog Browse UI, Event Detail & Admin Event Ops | v1.2 | 5/5 | ✅ Complete | 2026-06-06 |
| 18. Seed/Demo Harness for Multi-outcome + Categories | v1.2 | 1/1 | ✅ Complete | 2026-06-06 |
| LB-A/B/C. Live-Bets demo (off-grid) | v1.3 | done | ✅ Complete | 2026-06-06 |

**Known deferred at v1.2 close:** 2 Phase-14 live human-UAT checks (redbeat schedule reload + Gamma `tag_id` drift re-verify). Carried from v1.0/v1.1: 3 human-UAT + 3 verification gaps (Phase 12), and the **non-deferrable Spanish legal review** of ToS/token policy before any live operator demo (see [`STATE.md`](STATE.md) › Deferred Items).
