# Roadmap: XPredict

> Compact milestone-grouped view. Full v1.0 detail is archived in
> [`milestones/v1.0-ROADMAP.md`](milestones/v1.0-ROADMAP.md); phase execution history in
> [`milestones/v1.0-phases/`](milestones/v1.0-phases/). See [`MILESTONES.md`](MILESTONES.md) for shipped summaries.

## Milestones

- ✅ **v1.0 MVP** — Phases 1-12 (shipped 2026-06-04) — production-grade play-money prediction market, end-to-end.
- ✅ **v1.1 Demo Polish** — Fases A-E (shipped 2026-06-04) — brand-aware design system, seed/demo harness, player & operator polish, demo QA.
- 📋 **v2.0 (next)** — not yet planned. Run `/gsd-new-milestone` to scope (candidates: multi-tenancy runtime, real money, multi-outcome markets).

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
- [x] **Phase 11: Hardening & Operator-Demo Gate** — "Looks Done But Isn't" hardening checklist, demo gate.
- [x] **Phase 12: Admin Market Operations UI & Player Resolution Display** — v1.0 closure: admin markets list/create/edit/close + resolve/reverse/force-settle dialogs, per-market stake limits (BET-06), player resolution display (STL-06). Closed the open gaps from the 2026-06-02 audit.

</details>

<details>
<summary>✅ v1.1 Demo Polish (Fases A-E) — SHIPPED 2026-06-04</summary>

> Executed off the formal phase grid in parallel git worktrees and landed via PRs (not numbered phases).
> Plan-of-record: [`milestones/v1.1-MILESTONE-CONTEXT.md`](milestones/v1.1-MILESTONE-CONTEXT.md).

- [x] **Fase A: Design system brand-aware** — propagate `--brand-*` to primitives (CTAs, links, badges, focus, odds bar, charts) + brand typography (`next/font`) + motion tokens (`framer-motion`). *(PR #22)*
- [x] **Fase B: Seed & demo harness** — realistic seed (users, house + mirrored markets, open & resolved, bets with P&L, odds history) + `demo-reset`. *(PR #19)*
- [x] **Fase C: Player polish** — header-nav, microinteractions, weighted success states, non-silent errors + loading states, `not-found`/`global-error`, responsive. *(PR #22)*
- [x] **Fase D: Operator polish** — admin loading skeletons + responsive tables, panel completeness. *(PR #23)*
- [x] **Fase E: Demo QA / guion** — step-by-step sales script + E2E happy-path QA checklist. *(PR #24)*

</details>

### 📋 v2.0 (next) — not yet planned

Scope with `/gsd-new-milestone`. Deferred candidates carried from v1.0/v1.1: multi-tenancy runtime (MTN), real money + Stripe/KYC (RM), multi-outcome markets (MKT2), full Polymarket catalog, live-bets integration (LB).

## Progress

| Milestone | Scope | Status | Shipped |
|-----------|-------|--------|---------|
| v1.0 MVP | Phases 1-12 | ✅ Complete | 2026-06-04 |
| v1.1 Demo Polish | Fases A-E (PRs #19, #22, #23, #24) | ✅ Complete | 2026-06-04 |
| v2.0 | TBD | 📋 Not started | — |

**Known deferred at close** (carried into next milestone): 3 human-UAT scenarios + 3 verification gaps from Phase 12 (see [`STATE.md`](STATE.md) › Deferred Items).
