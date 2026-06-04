---
phase: 12
slug: admin-market-operations-ui-and-player-resolution-display
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-03
audited: 2026-06-04
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Backend = pytest + httpx ASGITransport + testcontainers Postgres; frontend = Vitest (.test.tsx → jsdom, .test.ts → node) + pnpm typecheck. No framework install needed — both are present.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Backend framework** | pytest + pytest-asyncio (`asyncio_mode="auto"`) + httpx ASGITransport + testcontainers Postgres |
| **Backend config** | `backend/pyproject.toml` `[tool.pytest.ini_options]` (testpaths=`tests`, markers `integration`/`unit`) |
| **Frontend framework** | Vitest + `@vitejs/plugin-react` (`environmentMatchGlobs`: `.test.tsx`→jsdom, `.test.ts`→node) |
| **Frontend config** | `frontend/vitest.config.ts` (+ `vitest.setup.ts`) |
| **Backend quick run** | `cd backend && uv run pytest tests/settlement tests/markets tests/bets -x` |
| **Backend full suite** | `cd backend && uv run pytest` |
| **Frontend quick run** | `cd frontend && pnpm test -- <file>` |
| **Frontend full suite** | `cd frontend && pnpm test && pnpm typecheck` |
| **Estimated runtime** | backend quick ~30–90s (testcontainers), frontend quick ~3–10s |

---

## Sampling Rate

- **After every task commit:** run the matching quick command (backend `uv run pytest tests/<area> -x` for a backend task; `pnpm test -- <file>` + `pnpm typecheck` for a frontend task).
- **After every plan wave:** `cd backend && uv run pytest` (full) + `cd frontend && pnpm test && pnpm typecheck`.
- **Before `/gsd-verify-work`:** full backend suite (CI-graded for the integration tier) + full frontend suite + typecheck green.
- **Max feedback latency:** < 90s (backend quick run with testcontainers).
- **Baseline note:** scan the phase commit range `origin/main..HEAD` — ~4 pre-existing Windows-only failures (3 WS-need-Redis, 1 gitleaks full-history) and the orphan `middleware.test.ts` are NOT regressions (per user memory).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 12-01-01 | 01 | 1 | STL-06, BET-06 | T-12-03 | Money columns Numeric(18,4), serialized as string | unit | `cd backend && uv run python -m scripts.lint_money_columns && uv run mypy app/markets && uv run alembic heads` | ✅ (model/schema/migration) | ✅ green |
| 12-01-02 | 01 | 1 | STL-06 | T-12-01 / T-12-02 | Winner persisted in settlement tx; no admin-only leak on public read | integration | `cd backend && uv run mypy app/settlement app/markets && uv run pytest tests/settlement tests/markets/test_public_router.py tests/admin/test_kpi.py -x -q` | ✅ extend (6 fakes + RESOLVED-200 + persist) | ✅ green |
| 12-01-03 | 01 | 1 | STL-06, BET-06 | — | Migration physically applied (columns exist) | cli | `cd backend && uv run alembic current` | ✅ migration | ✅ green |
| 12-02-01 | 02 | 1 | ADM-01..06, STL-02, STL-07 | T-12-05 | admin_jwt read server-side, never in client JS | unit | `cd frontend && pnpm typecheck` | ✅ new (api + types) | ✅ green |
| 12-02-02 | 02 | 1 | ADM-05, STL-02, STL-07 | T-12-06 | Settlement wrappers target BARE prefix (no /api/v1) | unit (node) | `cd frontend && pnpm test -- src/lib/__tests__/admin-markets-api.test.ts` | ✅ created (cloned admin-api.test.ts) | ✅ green |
| 12-02-03 | 02 | 1 | ADM-01 | — | Status chip a11y (aria-label) | unit (jsdom) | `cd frontend && pnpm test -- src/components/admin/__tests__/market-status-badge.test.tsx` | ✅ created | ✅ green |
| 12-03-01 | 03 | 2 | BET-06 | T-12-08 | Per-market limit enforced server-side, global fallback | integration | `cd backend && uv run mypy app/bets && uv run pytest tests/bets -x -q` | ✅ extend (per-market + NULL fallback) | ✅ green |
| 12-03-02 | 03 | 2 | BET-06 | T-12-09 | Stake stays string; client mirror UX-only | unit (jsdom) | `cd frontend && pnpm test -- src/components/order-entry-form.test.tsx && pnpm typecheck` | ✅ extend | ✅ green |
| 12-04-01 | 04 | 2 | STL-06 | — | Resolution fields typed string-or-null | unit | `cd frontend && pnpm typecheck` | ✅ self (lib/api.ts) | ✅ green |
| 12-04-02 | 04 | 2 | STL-06 | T-12-12 | Justification escaped React text (no dangerouslySetInnerHTML); loss neutral not red | unit (jsdom) | `cd frontend && pnpm test -- src/components/__tests__/market-resolution-panel.test.tsx && pnpm typecheck` | ✅ created | ✅ green |
| 12-04-03 | 04 | 2 | STL-06 | T-12-11 / T-12-13 | Own payout self-scoped by player cookie, never another user | unit | `cd frontend && pnpm typecheck` | ✅ self (markets/[slug]/page.tsx) | ✅ green |
| 12-05-01 | 05 | 2 | ADM-01 | T-12-17 | List server-driven; admin_jwt forwarded server-side | unit | `cd frontend && pnpm typecheck` | ✅ new (nav + table + page) | ✅ green |
| 12-05-02 | 05 | 2 | ADM-02, ADM-03, ADM-07, BET-06 | T-12-15 / T-12-16 | 422 maps to inline error; criteria disabled when bet_count>0; stake-as-string | unit (jsdom) | `cd frontend && pnpm test -- src/components/admin/__tests__/market-form.test.tsx && pnpm typecheck` | ✅ created | ✅ green |
| 12-06-01 | 06 | 3 | STL-02, STL-07, ADM-06, ADM-04 | T-12-18 / T-12-19 / T-12-21 | Mandatory justification client-blocked; bare-prefix wrappers; reverse no-re-resolution copy | unit (jsdom) | `cd frontend && pnpm test -- src/components/admin/__tests__/settlement-dialogs.test.tsx && pnpm typecheck` | ✅ created | ✅ green |
| 12-06-02 | 06 | 3 | STL-02, STL-07, ADM-05, ADM-06, ADM-04 | T-12-20 | Action buttons status/source-gated; admin-gated endpoints | unit | `cd frontend && pnpm typecheck && pnpm test -- src/components/admin/__tests__/settlement-dialogs.test.tsx` | ✅ new ([id] page + kpi link) | ✅ green |
| 12-06-03 | 06 | 3 | STL-06, ADM-01..07, STL-02, STL-07, BET-06 | — | SC#5: full operator→player loop through the UI, no raw API | manual (human-verify gate) | (blocking checkpoint — operator walk-through) | n/a | ✅ approved (Pol 2026-06-03) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `frontend/src/lib/__tests__/admin-markets-api.test.ts` — URL-prefix contract guard (clone `admin-api.test.ts`); THE most important new test (Pitfall 1). [12-02 Task 2] — 10 tests green
- [x] `frontend/src/components/admin/__tests__/market-status-badge.test.tsx` — 5-state chip. [12-02 Task 3] — 15 tests green
- [x] `frontend/src/components/__tests__/market-resolution-panel.test.tsx` — STL-06 display branch (WON/LOST/NO-BET/LOGGED-OUT + HTML-escape). [12-04 Task 2] — 10 tests green
- [x] `frontend/src/components/admin/__tests__/market-form.test.tsx` — required/min>max/ADM-07-disabled/422-mapping. [12-05 Task 2] — 4 tests green
- [x] `frontend/src/components/admin/__tests__/settlement-dialogs.test.tsx` — mandatory-justification + wrapper-call per dialog + reverse copy guard. [12-06 Task 1] — 12 tests green
- [x] Extend `backend/tests/settlement/test_resolve_market.py` + `test_settlement_router.py` + `test_force_settle.py` + `test_market_resolve_port.py` + `tests/admin/test_kpi.py` fakes to the NEW `mark_resolved` signature (these FAIL to compile until updated — the lockstep signal). [12-01 Task 2] — green
- [x] Add a RESOLVED→200 case to `backend/tests/markets/test_public_router.py`. [12-01 Task 2] — green
- [x] Extend `backend/tests/bets/test_bet_router.py` + `test_place_bet.py` with per-market limit + NULL-fallback cases. [12-03 Task 1] — green
- [x] No framework install needed — pytest + vitest are present.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SC#5 end-to-end operator→player resolution through the UI | STL-06, ADM-01..07, STL-02, STL-07, BET-06 | Spans all slices + a real admin/player session + visual confirmation; not a single automated assertion | 12-06 Task 3 blocking human-verify walk-through (9 steps) — **APPROVED by Pol 2026-06-03** |
| Migration 0010 apply on this Windows host | STL-06, BET-06 | Local Postgres/Docker is host-conditional (crypto-casino port conflicts); CI testcontainers applies it green | `cd backend && uv run alembic upgrade head` (or `docker compose up -d db` first); the file's single-head correctness is machine-verified via `alembic heads` — **confirmed `0010_phase12_resolution_stakes (head)` during this audit; testcontainers applied it for the 111 backend tests** |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (the only non-automated task is the final SC#5 human-verify gate)
- [x] Wave 0 covers all MISSING references (5 new frontend test files + the backend fake/case extensions)
- [x] No watch-mode flags (`pnpm test` runs `vitest run`; backend uses `pytest`, no `--watch`)
- [x] Feedback latency < 90s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-03

---

## Validation Audit 2026-06-04

Post-execution audit (State A). Cross-referenced every requirement against the tests that exist after execution and **ran the full automated map** on this host (Docker/testcontainers available, Node 22.22.3 / pnpm 9.15.0 / uv 0.11.16).

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

### Evidence (ground-truth runs)

| Tier | Command | Result |
|------|---------|--------|
| Frontend tests | `pnpm test -- admin-markets-api market-status-badge market-resolution-panel market-form settlement-dialogs order-entry-form` | **6 files / 60 tests passed** |
| Frontend typecheck | `pnpm typecheck` (`tsc --noEmit`) | **exit 0 — clean** (covers all `pnpm typecheck` tasks: 12-02-01, 12-04-01, 12-04-03, 12-05-01, 12-06-02) |
| Backend integration | `uv run pytest tests/settlement tests/markets/test_public_router.py tests/markets/test_admin_router.py tests/bets/test_bet_router.py tests/bets/test_place_bet.py tests/admin/test_kpi.py -q` | **111 passed in 21.47s** (testcontainers Postgres) |
| Backend static | `uv run python -m scripts.lint_money_columns` · `uv run mypy app/markets app/settlement app/bets` · `uv run alembic heads` | lint **exit 0** (2 benign `min_stake`/`max_stake` stake-bound warnings, not ledger-money) · mypy **clean, 25 files** · alembic **single head `0010_phase12_resolution_stakes`** |

### Notes

- Every automated task in the Per-Task Map is now confirmed **green by execution on this host** — not inferred from file existence. The integration tier (the meat of STL-06 persistence and BET-06 per-market limits) ran locally via testcontainers, so no CI-only deferral was needed for this audit.
- `wave_0_complete` flipped `false → true`: all 5 new frontend test files exist and pass; backend fake/case extensions exist and pass.
- The only non-automated task (12-06-03, SC#5 operator→player walk-through) is an inherent human-verify gate and was **APPROVED by Pol on 2026-06-03**.
- Phase remains **Nyquist-compliant** (`nyquist_compliant: true`): every requirement has automated verification that runs green.

**Audit verdict:** NYQUIST-COMPLIANT — 0 gaps, 15/15 automated tasks green, 1 manual gate approved.
