# Project Milestones: XPredict

Entries in reverse chronological order — newest first.

> **Note:** v1.0 and v1.1 were both shipped before being formally closed in `.planning/`. This ledger was
> created during a reconciliation on 2026-06-04 that archived v1.0 artifacts to `milestones/` and recorded
> v1.1 (which was executed off the formal phase grid, in parallel worktrees, and merged via PRs).

## v1.1 Demo Polish (Shipped: 2026-06-04)

**Delivered:** Elevated the demo from "works end-to-end" to "sells itself" — real white-label theming across the player surface, a realistic seed/demo harness, and player + operator polish, plus a step-by-step sales guion.

**Phases completed:** Fases A-E (executed off the numbered grid; landed via PRs #19, #22, #23, #24)

**Key accomplishments:**
- Brand-aware design system — `--brand-*` tokens propagated to all player primitives (CTAs, links, badges, focus, odds bar, charts) + brand typography (`next/font`) + motion (`framer-motion`); re-skins the whole player UI from `/admin/branding`.
- Seed & demo harness (entto-end #0 blocker) — one command stands up a credible demo (users, house + mirrored markets open *and* resolved, bets with P&L, odds history for charts); another resets it. Replaced the no-op `make seed`.
- Player polish — header-nav, microinteractions, weighted success states, non-silent errors + loading states on wallet/portfolio, branded `not-found`/`global-error`, responsive.
- Operator polish — admin page loading skeletons + responsive tables; panel completeness with no dead placeholders.
- Demo QA — sales script + cross-browser/responsive happy-path checklist for an infallible live demo.

**Stats:**
- 5 workstreams (Fases A-E), landed via 4 PRs (#19, #22 [A+C], #23, #24)
- ~2 days (2026-06-03 → 2026-06-04)
- Executed in parallel git worktrees (e.g. `xpredict-faseD`), merged to `main`

**Plan-of-record:** [`milestones/v1.1-MILESTONE-CONTEXT.md`](milestones/v1.1-MILESTONE-CONTEXT.md) · brief: [`milestones/v1.1-PHASE-B-BRIEF.md`](milestones/v1.1-PHASE-B-BRIEF.md)

**What's next:** v2.0 — not yet scoped. Candidates: multi-tenancy runtime, real money (Stripe/KYC), multi-outcome markets, full Polymarket catalog, live-bets integration.

---

## v1.0 MVP (Shipped: 2026-06-04)

**Delivered:** A production-grade, play-money white-label prediction market — browse a credible catalog (top-25 Polymarket mirror + house markets), bet with virtual balance, automatic + manual settlement with a double-entry ledger and immutable audit log, and a full admin/CRM with KPI dashboard and configurable branding.

**Phases completed:** 1-12 (~44 plans)

**Key accomplishments:**
- Production-grade money core — append-only double-entry ledger, `NUMERIC(18,4)`/`Decimal` (CI-enforced), ACID bets, `FOR UPDATE` + idempotency, non-negative + non-transferable constraints, nightly reconciliation.
- Auth & identity — Argon2id via fastapi-users, email verification, password reset, refresh-token rotation, per-IP/per-email rate-limiting; distinct admin auth surface.
- Markets — `MarketSource` Protocol with house adapter + Polymarket Gamma sync (Celery Beat + RedBeat lock, top-25, odds snapshots); UMA auto-resolution with grace window + admin force-settle override.
- Admin/operator — CRM (users, ban/unban, CSV export), immutable audit-log viewer, KPI dashboard (Recharts), single-row TenantConfig branding, full market operations UI (create/edit/close/resolve/reverse).
- Multi-tenant & real-money seams pre-built — `tenant_id` ghost columns, feature-flags table, Stripe stub interface — so v2 migration is mechanical.

**Stats:**
- 12 phases, ~44 plans; ~10 days (2026-05-25 → 2026-06-04)
- 69 v1 requirements (see archived [`milestones/v1.0-REQUIREMENTS.md`](milestones/v1.0-REQUIREMENTS.md))
- Stack: Python 3.12 · FastAPI · SQLAlchemy 2.0 async · Postgres 16 · Redis · Celery+redbeat · Next.js 15 · React 19 · Tailwind 4 · shadcn/ui
- v1.0 closure (Phase 12) merged via PRs #20/#21

**Known gaps at close** (from the 2026-06-02 audit, mostly closed by Phase 12; residuals deferred):
- 3 human-UAT scenarios open (Phase 12 `12-HUMAN-UAT.md`) + 3 verification gaps — see `STATE.md` › Deferred Items.

**What's next:** v1.1 Demo Polish (shipped 2026-06-04).

---
