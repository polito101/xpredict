# Project Milestones: XPredict

## v1.4 Premium Experience (Shipped: 2026-06-06)

**Phases completed:** 1 phase (Phase 19) · landed via PR [#33](https://github.com/polito101/xpredict/pull/33) (`2b2fca8`).

**Delivered:** A frontend-only premium redesign that repositions XPrediction as a white-label, API-first prediction-market **platform** — dark-first "Obsidian & Spark" design system, a platform-first public landing, the live app moved behind authentication, and a premium-restyled backoffice. **Zero backend domain changes** (one exception: a pure `ruff format` of the already-merged v1.3 livebets files to unblock CI).

**Key accomplishments:**

- Dark-first semantic token system via Tailwind v4 `@theme inline` (surface/card/popover/muted/border/ring/radius + gradient/glow/aurora utilities); identity primitives `XMark` / `Spark` / `Aurora`; Space Grotesk (display) + Inter (body); all 17 shadcn primitives retoned.
- Platform-first public landing at `/` (Hero node-graph → Pillars run/integrate/launch → Capabilities → API section → Demo with real `/catalog` stats + featured → How it works → CTA), resilient to a down backend (best-effort reads).
- App moved behind auth — edge middleware (`proxy.ts`) gates `/markets,/events,/portfolio,/wallet,/live` → `/login` and `/admin/*` → `/admin/login`; nav splits logged-out vs in; login → `/markets`, logout → `/`.
- Premium player surfaces (market/event detail, oversized live odds, dark gradient charts, portfolio performance hero, wallet big-number balance) + a dark-first brand-aware admin shell (no more double header) with tokenized backoffice + dark charts.
- Visible brand = **"XPrediction"** everywhere (runtime-driven via `/branding/current`, with the legacy `"XPredict"` default mapped for display); technical names stay `XPredict/xpredict` (cookie, env vars, repo) — no contract churn. White-label runtime branding preserved (real operator names still override).
- Invariants preserved under a 5-lens adversarial review (no HIGH/regression): white-label branding pipeline, money/odds as display strings, per-outcome framing-LOCK (independent YES bars, never sum-to-100), single live-socket cap, escaped justification, A-LOSS-NEUTRAL.

**Stats:** 238/238 frontend vitest (37 frontend + 3 v1.3 live files), `pnpm typecheck`/`lint` clean, `next build --webpack` green (16 routes); CI `frontend` + security checks green. Backend integration is handed to Pol (env wiring + `brand_name` + official logo PNG drop) — see [`v1.4-MILESTONE-CONTEXT.md`](milestones/v1.4-MILESTONE-CONTEXT.md) and the per-phase HANDOFF.

**What's next:** undefined — run `/gsd-new-milestone`. Candidates: multi-tenancy runtime, real money (Stripe/KYC), full Polymarket catalog, live-bets productionization.

---

## v1.3 Live-Bets demo (Shipped: 2026-06-06, off-grid)

**Phases completed:** Fases LB-A/B/C (off the formal phase grid, like v1.1) · landed via direct merge `171aee5` (`Merge gsd/livebets-demo into main`).

**Delivered:** Embed **live-bets** (B2B multi-player vehicle-traffic betting, HLS-synced) inside XPrediction, which acts as the live-bets **operator** — a player bets from a new `/live` route and their single XPrediction wallet is debited on placement and credited on win (one balance, play-money). Demo-only, **additive** (does not touch v1.2 files).

**Key accomplishments:**

- **LB-A Backend bridge** — `app/integrations/livebets/` (httpx client + `LiveBetsBridge` + router) + an additive migration (`livebets_escrow` system account + `livebets_bets` mirror table) + config. Event-driven idempotent ledger mirror (debit on `bet-placed`, credit on settle), server-verified via `GET /v2/bets/{id}`, idempotent by `bet_id`; per-player ownership (IDOR-safe); non-finite-amount rejection + stake hardening. 23505 session-per-call discipline preserved.
- **LB-B Frontend surface** — `/live` Server Component embedding `<live-bets-table>` in XPrediction chrome + wallet; the four widget DOM events wired to placed/settled Server Actions with in-island wallet refresh; "Live" nav entry; HttpOnly cookie; backend-keyed settle toasts. Component + money-path tests.
- **LB-C Demo harness** — isolated live-bets instance (CORS, full-scope operator key), ingest clips + a round orchestrator, env wiring + a demo runbook. E2E proven: a bet from `/live` moves the XPrediction wallet. Real contract drift vs the v3 guide fixed (`GET /tables`, `BetView.id/selection`, `/v2/sessions` Idempotency-Key).

**Decisions:** unified wallet (XPrediction ledger is the single balance) · embed the widget (not rebuild) · mirror by events (Approach A, DOM-driven, server-verified, idempotent).

**Out of scope (demo):** real money/PSP · OAuth client_credentials · OTEL passthrough · production webhook hardening (HTTPS/DLQ) · bulletproof cross-DB reconciliation · live-bets catalog/lobby. Design contract: [`docs/superpowers/specs/2026-06-05-live-bets-integration-design.md`](../docs/superpowers/specs/2026-06-05-live-bets-integration-design.md). Plan-of-record: [`v1.3-MILESTONE-CONTEXT.md`](milestones/v1.3-MILESTONE-CONTEXT.md); audit: [`v1.3-MILESTONE-AUDIT.md`](milestones/v1.3-MILESTONE-AUDIT.md).

---

## v1.2 Credible Catalog (Shipped: 2026-06-06)

**Phases completed:** 6 phases, 20 plans, 24 tasks

**Key accomplishments:**

- Event-of-binaries database seam: reversible migration 0011 creates `market_groups` + nullable `Market.group_id`/`group_item_title` + pg_trgm + 6 catalog/search indexes, with a `MarketGroup` ORM model and a `lazy="raise"` no-cascade relationship — pure additive, existing binary markets byte-for-byte unchanged.
- Wave-2 automated Nyquist proof for every Phase 13 SC: a new migration-introspection test (apply + reversibility + chain + pg_trgm + all 6 indexes via raw `pg_indexes.indexdef`) and a `MarketGroup` ORM round-trip extension (selectinload >=2 children + `lazy="raise"` + `group_id IS NULL` regression) — 117 markets tests + 92 bets/settlement tests green, money-lint clean.
- GammaEvent/GammaTag/GammaEventMarket Pydantic parsers + first-by-priority `resolve_category` + the version-controlled 7-entry `POLYMARKET_CATEGORIES` allow-list, with the event-level FLOAT-volume→Decimal divergence proven by unit tests against live-captured fixtures.
- `GammaClient.fetch_events(tag_id=...)` — a single ranked `GET /events` (volume24hr desc, active/open, CAT-05 500-cap, offset-paging-ready) on the verbatim-reused fetch_top_markets retry/pool, plus a corrected per-endpoint rate-limit docstring.
- Extracted `_upsert_one_market` (now stamping `category` + `group_id` + `group_item_title`) from `sync_top25`, then built `sync_events` + `_upsert_market_group` on top — the first writer of the Phase-13 `market_groups` seam: 1 group + N stamped children for multi-outcome events, a standalone child (no group) for `len==1` events (EVT-07), idempotent on `ON CONFLICT (source, source_event_id)`, with a SAVEPOINT-guarded slug-collision retry.
- Wired the curated sync end-to-end: `_run_poll_events` loops the 7 `POLYMARKET_CATEGORIES` in priority order (fetch `/events` -> cross-cycle event-id dedup -> `$10k` volume24hr floor AFTER dedup -> top-N -> `sync_events` -> commit-per-category with per-category keep-last-good), behind a distinct `EVENTS_LOCK_KEY` WR-05 lock; swapped the beat schedule from `poll-polymarket-top25`@30s to `poll-polymarket-events`@300s (legacy task kept importable); inverted the existing beat-schedule test and proved the distinct lock + keep-last-good + dedup-before-floor with mocked Redis/Gamma.
- Column-free `derive_event_status(children)` pure projection (open/partially_resolved/resolved/void) plus its `ChildStatus` frozen-slots input, in the new `event_service.py`, with 8 no-Docker unit tests covering all four states + empty + the void edge.
- `EventService.resolve_event` / `void_event` compose the UNCHANGED `SettlementService` over a `MarketGroup`'s children — one FRESH session per child (the 23505 dangling-tx landmine), winner→YES / losers→NO (resolve) or all-children→NO (void) — with a mirrored-reject gate, a non-blank-justification guard, case-insensitive YES/NO mapping, and one extra event-level audit row, proven by a 12-test integration suite asserting spike-004 `drift_count == 0` after resolve / void / partial-failure / idempotent replay.
- `EventService.reverse_event` composes the UNCHANGED `SettlementService.reverse_settlement` over a house event's settled children — one FRESH session per child (23505-safe AND per-child `CHECK(balance>=0)` floor isolation), idempotent, mirrored-rejecting, with one `event.reversed` audit row — plus a new `test_event_mirrored.py` proving (verify-only, `tasks.py` NO diff) that a `source=POLYMARKET` `market_group`'s children auto-settle through the existing `detect_polymarket_resolutions` UMA path and that `reverse_event` refuses mirrored groups; all 26 settlement-event tests green with spike-004 `drift_count == 0` on every reverse / partial-reverse / mirrored path.
- Wave-0 `tests/catalog/` package — a shared httpx AsyncClient/ASGITransport fixture plus a seed-factory module that builds standalone markets and ≥2-child events drivable to open/partially_resolved/resolved/void states, with ledger-backed bets via `WalletService.recharge`.
- Catalog & event HTTP API (Phase 16): browse/search/category/event-detail reads (pg_trgm ILIKE, bounded `LIMIT 100`, explicit-empty for every filter combo) + house-event CRUD + resolve/void/reverse endpoints with a server-side two-step confirm — `catalog/{router,service,schemas}.py` + `settlement/event_router.py`, mounted in `main.py`.
- Player catalog browse + multi-outcome event detail (Phase 17): per-outcome independent YES rows that NEVER sum to 100%, bet on a single child via the existing binary path, plus admin event ops (create/edit/resolve/void/reverse dialogs); 36 new frontend tests; a real duplicate-socket leak caught + fixed.
- One-command demo seed (Phase 18): a marquee multi-outcome event per category across all 4 states, driven through the MERGED service layer, with an idempotent reset + a green integrity self-check — the milestone's end-to-end acceptance test.

**Known deferred at close:** 2 (Phase 14 live human-UAT — redbeat reload + Gamma `tag_id` drift; see STATE.md › Deferred Items).

---

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
