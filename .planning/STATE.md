---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: verifying
last_updated: "2026-05-29T17:19:33.931Z"
last_activity: 2026-05-29
progress:
  total_phases: 11
  completed_phases: 6
  total_plans: 27
  completed_plans: 24
  percent: 55
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-25)

**Core value:** El operador puede ofrecer un catálogo creíble de mercados de predicción (mezcla de Polymarket y house) con liquidación correcta y CRM para gestionar usuarios, todo bajo su marca — sin construir ni operar la pieza técnica.
**Current focus:** Phase 9 — User App UX Polish (Market Detail & Real-Time)

## Current Position

Phase: 9 (User App UX Polish (Market Detail & Real-Time)) — EXECUTING
Plan: 4 of 4
Status: Phase complete — ready for verification
Last activity: 2026-05-29

Progress: [█████████░] 89%

## Performance Metrics

**Velocity:**

- Total plans completed: 13
- Average duration: ~21min
- Total execution time: ~83min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Scaffold & Foundations | 4/4 | ~83min | ~21min |
| 2. Auth & Identity | 0/TBD | — | — |
| 3. Wallet & Ledger | 0/TBD | — | — |
| 4. Markets Domain & HouseAdapter | 0/TBD | — | — |
| 5. Bets & Settlement (house only) | 0/TBD | — | — |
| 6. Polymarket Sync | 0/TBD | — | — |
| 7. Polymarket Auto-Resolution | 0/TBD | — | — |
| 8. Admin CRM | 0/TBD | — | — |
| 9. User App UX Polish | 0/TBD | — | — |
| 10. Admin Dashboard & Branding | 0/TBD | — | — |
| 11. Hardening & Demo Gate | 0/TBD | — | — |
| 01 | 4 | - | - |
| 02 | 5 | - | - |

**Recent Trend:**

- Last 5 plans: 01-04 closeout (~32min cumulative; 6 atomic commits: feat for gitleaks, chore for CI/dev-loop, style for ruff format alignment, docs for SUMMARY skeleton, docs for STATE/ROADMAP, docs for closeout; 41/41 backend tests pass + 2/2 frontend; Phase 1 acceptance gate auto-approved per --auto mode — 3.5/5 ROADMAP SC ✓ machine-verified, 1.5/5 deferred as documented manual-verify items); 01-03 (13min, 3 atomic commits, 9 integration tests + 30 unit = 39/39 green, docker compose config + alembic heads clean, 3 Rule-3 auto-fix deviations all infra-level + Task 3 runtime acceptance manual-verify gated by host port conflicts); 01-02 (12min, 2 atomic commits, 2 Vitest tests green, pnpm build/typecheck clean, 6 auto-fix deviations all scaffold-level); 01-01 (26min, 3 atomic commits, 30 tests passing, ruff/mypy/money-lint clean)
- Trend: Phase 1 execution complete — all 4 plans shipped within the day; PLT-04 negative-test acceptance machine-verified (`tests/test_gitleaks_blocks_secret.py` 2/2 green); pre-commit + 3 GitHub Actions workflows + bin/dev/Makefile/README all shipped. Manual-verify items (SC#1 docker compose runtime + SC#5 Sentry round-trip) move to the `/gsd-verify-work 1` audit step; Pol's 5-15 min checklist (in 01-04-SUMMARY.md + 01-03-SUMMARY.md) closes them before `/gsd-ship`.

*Updated after each plan completion*
| Phase 03 P01 | 12min | 3 tasks | 10 files |
| Phase 03 P02 | ~8min | 2 tasks | 4 files |
| Phase 03-wallet-double-entry-ledger P06 | ~26min | 2 tasks | 3 files |
| Phase 03-wallet-double-entry-ledger P03 | ~5min | 2 tasks | 2 files |
| Phase 03-wallet-double-entry-ledger P04 | ~13min | 3 tasks tasks | 5 files files |
| Phase 03-wallet-double-entry-ledger P05 | ~10min | 3 tasks | 8 files |
| Phase 09-user-app-ux-polish-market-detail-real-time P01 | ~30min | 3 tasks | 18 files |
| Phase 09-user-app-ux-polish-market-detail-real-time P02 | 6min | 2 tasks | 5 files |
| Phase 09-user-app-ux-polish-market-detail-real-time P03 | ~33min | 3 tasks | 12 files |
| Phase 09-user-app-ux-polish-market-detail-real-time P04 | 8min | 2 tasks | 11 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- 2026-05-25: Vertical MVP mode + fine granularity (11 phases) approved by Pol.
- 2026-05-25: HouseAdapter built before PolymarketAdapter (Phase 4 → 6) — proves `MarketSource` Protocol with controllable data and unlocks demoable happy path at Phase 5 without external dependency.
- 2026-05-25: `SettlementService` built once in Phase 5, reused unchanged in Phase 7 for Polymarket auto-resolution — the architectural payoff of the `MarketSource` abstraction.
- 2026-05-25: Phase 1 locks money-column standards (`NUMERIC(18,4)` + Python `Decimal` from strings), `tenant_id` ghost column, audit-log immutability trigger — non-renegotiable foundations.
- 2026-05-25: Phase 11 is the operator-demo gate; ToS + regulatory posture review is part of it (per PITFALLS.md §"The Regulatory Line").
- **2026-05-26: Phase 1 ownership transfer to Pol.** Cuco was originally going to plan + implement Phase 1; Pol decided to do it himself. Context gathered in `--auto` mode — 47 decisions D-01..D-47 captured in `.planning/phases/01-scaffold-foundations/01-CONTEXT.md`. Locks: docker-compose with 8 services (db/redis/mailpit/backend/worker/beat/flower/frontend), modular monolith feature folders, `uv` for Python deps, `pnpm` for frontend, Alembic baseline migration creates only Phase 1 tables (`audit_log`, `feature_flags`), audit-log immutability via both Postgres trigger AND `REVOKE`, structlog (console in dev / JSON in prod), Sentry single project per env with `service=*` tag, money-column AST lint script in `scripts/`, `Money` SQLAlchemy alias for `Decimal` + `Numeric(18,4)`.
- **2026-05-26 (Plan 01-01 complete): Python pin broadened to `>=3.12,<3.14`.** STACK.md fixed `<3.13`, but Pol's host has only Python 3.13.7. uv still auto-fetches 3.12 on demand if a downstream environment needs strict 3.12-only. 3.13 is FFI-compatible with every locked dep (asyncpg 0.31, psycopg2-binary 2.9.10, sqlalchemy 2.0.50, etc.).
- **2026-05-26 (Plan 01-01): Money-lint annotation-kind classifier.** D-17 lists `value` in `MONEY_NAMES`, but `feature_flags.value` is a legitimate JSONB column. Added an annotation-kind classifier (`numeric` / `non-money` / `unknown`) — R2 only fires when `Mapped[T]` is numeric or unclear. Tightens the lint without weakening it; documented in `backend/CONVENTIONS.md` §1 and tested in `tests/test_money_lint.py::test_jsonb_value_passes`.
- **2026-05-26 (Plan 01-01): Lazy engine factory + lazy session-maker in `app/db/session.py`.** Avoids constructing asyncpg pool at module import; makes `Settings()`-required tests trivial and unblocks `app.celery_app` imports during pytest collection.
- **2026-05-26 (Plan 01-02): Pinned `next@^15.5.18` (NOT 16+).** `create-next-app@latest` defaulted to Next 16.2.6 but STACK.md §4.1 locks Phase 1 on Next 15. Rewrote `frontend/package.json` by hand. Affects Phase 8+ frontend work — they inherit 15.x patterns (`async cookies()/headers()`, `withSentryConfig` wrapper, `instrumentation.ts` shape).
- **2026-05-26 (Plan 01-02): Frontend `test` script `vitest` → `vitest run`.** pnpm 9.x parses `pnpm test --run` as an unknown pnpm option; non-watch is the right CI default. `test:watch` added for the dev loop. Affects Plan 01-04 CI workflow + Phase 2+ frontend test conventions.
- **2026-05-26 (Plan 01-02): `@sentry/nextjs` pinned to `^10.53`.** Source-map upload disabled in Phase 1 (`sourcemaps.disable=true`) — Phase 11 polish re-enables for staging. Frontend Sentry `initialScope.tags.service='frontend'` on BOTH `instrumentation.ts` (server) AND `instrumentation-client.ts` (browser) — mirrors Plan 01-01 backend tagging shape so all 4 Sentry surfaces share a single filter (CONTEXT D-27).
- **2026-05-26 (Plan 01-03): `TENANT_DEFAULT = "00000000-0000-0000-0000-000000000001"` defined once at the top of `0001_phase1_foundations.py` and reused on both `audit_log` and `feature_flags`** — Pitfall 10 mitigation. Single source of truth for the v1 default UUID; grep returns exactly one definition.
- **2026-05-26 (Plan 01-03): `pytest_asyncio.fixture(loop_scope="session")` for engine + async_session.** pytest-asyncio 0.25 defaults to function-loop on async fixtures; without `loop_scope="session"` the session-scoped engine fixture's asyncpg pool errors with "Event loop is closed" on the second test. Each integration test file also sets `pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]`. Phase 2+ integration tests inherit this shape.
- **2026-05-26 (Plan 01-03): Frontend Dockerfile pnpm pin to 9.15.0.** `corepack prepare pnpm@latest --activate` resolves to pnpm 11 which requires Node ≥22.13; node:20-alpine is the locked image. Pinned to 9.15.0 (matches the host pnpm + lockfile generator from Plan 01-02). Surgical 1-line fix; no frontend source touched.
- **2026-05-26 (Plan 01-03): Task 3 runtime acceptance documented as manual-verify.** Host port conflicts with Pol's `crypto-casino` `cc_redis` (port 6379) and `cc_postgres` (port 5432) containers prevented `docker compose up -d --wait` from binding. 5-min manual checklist captured in `01-03-SUMMARY.md §"Task 3 — Runtime Acceptance (Manual-Verify)"` (stop cc_*, run compose, verify 8 healthy, run alembic + HTTP triple-trigger, restart cc_*).
- **2026-05-26 (Plan 01-04): `.gitleaks.toml` allowlist extended to cover `.planning/*`.** Beyond the D-33 baseline (`tests/.*fixtures.* + docs/*.md + README*.md + .gitleaks.toml`), Pol's GSD planning artifacts contain example secret strings (e.g., `SESSION_SIGNING_KEY=…` mentions in 01-CONTEXT.md D-33). The `.planning/*` allowlist path keeps the linter from flagging its own context documents. In-spec extension of D-46.
- **2026-05-26 (Plan 01-04): Three-tier secret-scanning architecture committed.** Pre-commit `gitleaks protect --staged` (developer machine, sub-second) → backend-ci.yml `gitleaks/gitleaks-action@v2` (every PR diff) → security.yml `fetch-depth: 0` weekly cron (full-history sweep). Different latency/coverage tradeoffs per tier per Pitfall 9; pre-commit is the recommendation (can be bypassed `--no-verify`), CI is the gate (cannot bypass on `main`).
- **2026-05-26 (Plan 01-04): Phase 1 acceptance gate auto-approved per --auto mode.** 3.5/5 ROADMAP Success Criteria machine-verified; 1.5/5 deferred as documented manual-verify items (environmental, not implementation gaps). User response `"approved"` recorded; closeout commit captured the auto-approval rationale. Manual-verify items (SC#1 docker-compose runtime + SC#5 Sentry event round-trip) move to the `/gsd-verify-work 1` audit step.
- **2026-05-27 (Plan 03-01): Wallet ledger schema shipped.** accounts/transfers/entries (UUID PKs, NUMERIC(18,4) money via `Mapped[Money]`, version column, tenant_id ghost) created by migration `0003_phase3_wallet_ledger` (single head off `0002_phase2_auth`). Immutability ported from the Phase 1 audit_log pattern, generalized to a shared `raise_ledger_immutable()` deny-trigger + `REVOKE UPDATE, DELETE` applied to `transfers` + `entries` ONLY (accounts.balance is a mutable denormalized cache). `CHECK (balance >= 0)` (WAL-08) + `idempotency_key UNIQUE` enforced and DB-verified. 8 Wave-0 integration tests green against testcontainers Postgres (tenant_id default, CHECK→23514, append-only UPDATE/DELETE blocked, idempotency→23505, seeded singletons). Requirements WAL-06 + WAL-08 complete.
- **2026-05-27 (Plan 03-01): house_promo / house_revenue UUIDs fixed in `app/wallet/constants.py`** (`…00a1` / `…00a2`) and seeded by migration 0003 (ON CONFLICT DO NOTHING). house_promo funded with `1000000000.0000` so admin recharges (which debit it) never underflow the balance floor in v1. The recharge service (03-04) and settlement (Phase 5) reference these singletons directly — no runtime lookup-by-kind.
- **2026-05-27 (Plan 03-01): Integration-test savepoint discipline.** Statements expected to raise a `DBAPIError` (CHECK/trigger/UNIQUE violations) must be wrapped in `async_session.begin_nested()` so the abort is savepoint-scoped and does not poison the shared session-scoped transaction. Without this, the next test fails with `InFailedSQLTransactionError`. NOTE: the pre-existing `tests/core/test_audit_immutability.py` has this latent flaw (fails on its 4th test under `-x`) — out of scope for this plan, logged for a follow-up retrofit.
- [Phase 03]: Plan 03-02: WalletService shipped as the single race-safe ledger writer (WAL-07) -- FOR UPDATE inside one session.begin(), atomic paired-entry double-entry, 23505->return-existing idempotency, canonical UUID lock order; ported from the validated spike harness. SC#2 signature gate (50 concurrent overdraft -> drift 0, balance exact, 25/25 succeed/reject) green on production code. Added public WalletService.transfer (balance-checked debit->credit primitive recharge specializes + Phase 5 bets reuse); fixed recharge autobegin (resolve wallet INSIDE session.begin()); create_wallet is add+flush only (caller-owned tx, SC#1). — Faithful harness port keeps every concurrency/atomicity invariant in one place; the transfer primitive was required to drive the overdraft gate on production code since recharge debits the billion-funded house_promo and never rejects.
- [Phase 03]: 03-06: reconcile_wallets nightly Celery task (RedBeat 03:00 UTC) sums SUM(credit)-SUM(debit) per account vs accounts.balance; clean->INFO, drift->CRITICAL + Sentry (SC#7/PLT-09); sync task wraps asyncio.run
- [Phase 03]: 03-06: seeded house_promo singleton excluded from reconciliation (1e9 opening balance is a deliberate non-ledger-backed seed); reconciling it would emit a nightly false CRITICAL/Sentry alert (alert fatigue)
- [Phase ?]: Plan 03-03: UserManager.create override (RESEARCH Option A) co-inserts the user_wallet on the adapter's own session between the user INSERT and a SINGLE commit -- user + wallet land atomically (SC#1/WAL-01). The stock fastapi-users SQLAlchemyUserDatabase.create() commits BEFORE on_after_register fires (verified in installed v15.0.5 source), so the hook can never host same-transaction work (Pitfall 1); the override is the fix. WalletService.create_wallet stays add+flush-only (caller-owned tx). Fault injection proves a wallet-creation failure rolls the user back too (no orphan).
- [Phase ?]: [Phase 03]: 03-04: POST /admin/wallets/{user_id}/recharge -- first money-moving endpoint. Admin-Bearer-gated (current_active_admin), Idempotency-Key required (400 if absent), debits house_promo + credits path user only via WalletService.recharge, money-as-string response (MoneyStr=Annotated[Decimal,PlainSerializer]), wallet.recharge audited. SC#5/WAL-09 firewall: RechargeRequest extra=forbid (no destination field -> dst_user_id is 422) + route inventory + Entry.account_id FK targets accounts only. Audit is action-THEN-audit (recharge self-commits its session.begin(); handler audits + commits after) mirroring the auth surface, NOT same-tx-as-transfer -- avoids rewriting validated 03-02 concurrency code. Two Rule-1 fixes: pre-read autobegan tx -> rollback() before recharge.begin(); session churn expired admin/transfer ORM instances -> capture .id as plain values before commit (MissingGreenlet). WAL-09 complete.
- [Phase ?]: [Phase 03]: 03-05: player wallet read surface — GET /wallet/me/balance (WAL-03) + GET /wallet/me/transactions (WAL-04), cookie-gated by current_active_player + strictly self-scoped (NO user_id param -> cross-user read structurally impossible, T-03-18); money as JSON string via MoneyStr (SC#4, asserted on the raw wire); get_transactions is read-only offset pagination over the caller's own entries. SC#6/PLT-05 Stripe stub: recharge(payment_provider='stripe') raises NotImplementedError (in the quick non-integration run) + DISABLED 'Add funds' button on the new Next.js /wallet page. Rule-1 fix: wallet/router.py OMITS 'from __future__ import annotations' (FastAPI 3.13 mis-resolved Annotated[Depends] as query params -> 422) — same constraint admin_router.py documents. Phase 3 COMPLETE (6/6).
- [Phase ?]: 2026-05-29 (Plan 09-01): Real-time WS price-broadcast backend (MKT-04) shipped — spike-003 pipeline (ConnectionManager + redis.asyncio psubscribe(prices:*) subscriber + public /ws/markets/{market_id}) lifted verbatim into app/realtime/ and wired into the app/main.py lifespan (one subscriber task per worker -> multi-worker correct). Two producer hooks publish a lean string-odds delta {type,market_id,outcomes:[{outcome_id,odds}],ts} to prices:{market_id} POST-COMMIT only (Pitfall 3): admin odds edit publishes in the router after session.commit(); the Polymarket poll publishes via its held AioRedis after commit, per-market, on-change only (Pitfall 4). MarketService.update_market now returns (market, odds_deltas) so the router owns the post-commit publish; format_odds quantizes to Numeric(8,6) so the socket string == the REST OutcomeRead string. ZERO new backend deps; NO new Celery Beat entry. All automated checks green (4 producer, 127 non-integration, 100 realtime+markets+polymarket; ruff/mypy/money-lint clean). Browser round-trip is documented manual-verify (Plan 09-03 builds the frontend socket).
- [Phase ?]: 2026-05-29 (Plan 09-03): Frontend real-time slice + Recharts foundation (MKT-03/04) shipped — the single highest-risk phase item (Recharts blank on React 19) is NEUTRALIZED: react-is pinned to the exact installed React (19.2.6) + a pnpm.overrides.react-is="$react-is" block collapses ALL transitive react-is (was 16.13.1 + 17.0.2 in dev tooling) to one version — `pnpm why react-is` reports a SINGLE version, gated by a chart-not-blank smoke test that asserts a real Recharts path.recharts-line-curve renders under jsdom (ResizeObserver + getBoundingClientRect stubbed; the react-is sentinel). Shipped: PriceHistoryChart ("use client" emerald-600 YES line + zinc grid + h-64 sized parent + 24h/7d/30d toggle defaulting 7d + <2-snapshot empty state); useMarketSocket (ports spike 003 — connects ${NEXT_PUBLIC_WS_URL}/ws/markets/{id}, Live→Stale(>30s, KEEPS odds — Pitfall 5)→Reconnecting with exponential backoff capped 30s+jitter, periodic ping, ignores non-price_update, full unmount cleanup; proven by a fake-timers + stub-WebSocket state-machine test); LiveIndicator (dot+label per ConnState, aria-live=polite); lib/api.ts fetchMarket/fetchPriceHistory/fetchActivity + MarketDetail/PriceHistoryResponse/ActivityItem/PricePoint/PriceWindow + MarketNotFound (money/odds as strings, SP-1); hand-copied shadcn dialog+select (new-york) wrapping @radix-ui/react-dialog@1.1.15 + react-select@2.2.6. NEXT_PUBLIC_WS_URL documented in the single root .env.example + docker-compose frontend env. pnpm driven via `corepack pnpm` (not on PATH in this Windows worktree). 3 atomic feat commits; chart 4 + hook 4 tests green; pnpm build clean. KNOWN PRE-EXISTING (out-of-scope, logged to deferred-items.md): src/__tests__/middleware.test.ts imports ../middleware but the file was renamed ../proxy in 02-05 — breaks repo-wide `pnpm typecheck` (1 error) + the full `pnpm test` (1 suite fails to LOAD; all 45 actual tests still pass). Every 09-03 source file is type-clean; next build (app-graph typecheck) exits 0. The market-detail PAGE that composes these pieces + the order form is Plan 09-04.
- [Phase ?]: 2026-05-29 (Plan 09-02): Market-detail backend READ surface (MKT-03) shipped — two public endpoints on public_market_router. GET /{slug}/price-history?window=24h|7d|30d returns raw 5-min OddsSnapshot YES points for 24h/7d and a 30d series DOWNSAMPLED server-side via Postgres DISTINCT ON (date_trunc('hour', snapshot_at)) ORDER BY bucket, snapshot_at DESC — latest snapshot per hour bucket, then a Python re-sort ascending for the chart — so the browser never receives ~8640 raw points (T-09-07). The window is a FastAPI Literal[24h,7d,30d] so an out-of-allowlist value 422s before the service runs, and the cutoff is derived from _WINDOW_CUTOFFS, never SQL-interpolated (T-09-08). GET /{slug}/activity returns the last-20 bets anonymized SERVER-SIDE with two independent guards: the SELECT projects only (stake, created_at, outcome.label) and ActivityItem has no user_id/email/display_name field (T-09-05); tests assert both the schema field set AND the raw HTTP JSON body. Money/odds serialize as strings via field_serializer (SP-1). The two routes are siblings of /{slug}/bet-check so they do not shadow bare GET /{slug}. Verified against real testcontainer Postgres: full tests/markets/ 86 passed. ZERO new deps, ZERO migrations (read-only over existing models).
- [Phase ?]: 2026-05-29 (Plan 09-04): Player market-detail page /markets/[slug] + order entry shipped (MKT-03) — Phase 9 COMPLETE (4/4). Async Server Component SSR-fetches market+price-history+activity in parallel (Promise.allSettled: market read is the 404 gate, history/activity degrade to empty), two-column grid grid-cols-1 lg:grid-cols-3 with always-visible Resolution criteria + sticky lg:top-8 order panel. OrderEntryForm (rhf+zod) -> BetConfirmDialog -> placeBetAction cookie-forward POST /bets; each backend status (402/409/403/422/401) maps to its SPECIFIC inline role=alert copy, NO toast (T-09-12/13). 403 disambiguates banned vs unverified on the FastAPI detail text. Composed Plan 03 pieces (chart/socket/LiveIndicator/dialog/select) + Plan 02 endpoints via two thin client wrappers (MarketDetailLiveOdds, PriceHistorySection) bridging the SSR page to client-only hooks (SP-5). Anonymized RecentActivityFeed (no user-id field — T-09-14) + MarketDetailSkeleton + portfolio loading.tsx (no layout shift). ZERO new deps. 7 order-form tests + 52/52 suite green; pnpm build exits 0. Only repo-wide failure is the pre-existing DEF-FE-01 orphan middleware.test.ts (out of scope, in deferred-items.md).

### Pending Todos

[From .planning/todos/pending/ — ideas captured during sessions]

None yet.

### Blockers/Concerns

[Issues that affect future work]

- **Phase 3 spike recommended**: Concurrent locking patterns in SQLAlchemy 2.0 async (`SELECT ... FOR UPDATE` inside `AsyncSession.begin()`, deadlock ordering, retry-on-serialization-failure) are non-obvious. Recommend `/gsd-spike` before Phase 3 planning. References: PITFALLS.md §Wallet, STACK.md §3.
- **Phase 6 spike recommended**: Gamma API schema quirks (stringified JSON in `outcomes`/`outcomePrices`, mixed string-vs-number numerics, `umaResolutionStatus` value space). Recommend `/gsd-spike` + VCR fixture capture on day 1 of planning. References: STACK.md §2.2, PITFALLS.md #2 + #9.
- **Phase 11 dependency**: Spanish legal counsel must review ToS and token policy before any demo to an operator. Not deferrable; this is a gating dependency on Phase 11 completion.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| (none) | — | — | — |

## Session Continuity

Last session: 2026-05-29T17:19:33.923Z
Stopped at: Completed 09-04-PLAN.md (market-detail page + order entry) — Phase 9 COMPLETE (4/4), ready for verification
Resume file: None
