---
phase: 9
slug: user-app-ux-polish-market-detail-real-time
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-29
updated: 2026-05-29
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> `workflow.nyquist_validation: true` — every task has an `<automated>` verify or a Wave 0 dependency.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework (backend)** | `pytest` + `pytest-asyncio` (`loop_scope="session"` for integration); markers `integration`, `asyncio` |
| **Framework (frontend)** | `vitest` + `@testing-library/react` + `jsdom` (`pnpm test` = `vitest run`) |
| **Config file** | backend: `backend/pyproject.toml` pytest config · frontend: `frontend/vitest.config.*` (Phase 1 scaffold) |
| **Quick run command (backend)** | `cd backend && uv run pytest -x -m "not integration"` |
| **Quick run command (frontend)** | `cd frontend && pnpm test` |
| **Full suite command** | backend: `cd backend && uv run pytest` (incl. realtime integration vs the docker-compose `redis` service) · frontend: `cd frontend && pnpm test && pnpm build` |
| **WS test client** | `websockets` library (test-only — ships with `fastapi[standard]`; else `uv add --dev websockets`); spike 003 `spike_ws_test.py` is the template |
| **Estimated runtime** | backend quick ~25s · backend full (with redis integration) ~60-90s · frontend ~15-30s |

> **fakeredis caveat:** the WS fan-out integration tests run against the REAL docker-compose `redis` service (marked `integration`); fakeredis cross-connection pub/sub semantics are unreliable (RESEARCH Validation Architecture note).

---

## Sampling Rate

- **After every task commit:** `cd backend && uv run pytest -x -m "not integration"` + `cd frontend && pnpm test` (the relevant new files).
- **After every plan wave:** `cd backend && uv run pytest` (incl. realtime integration + testcontainers) + `cd frontend && pnpm test && pnpm build`.
- **Before `/gsd-verify-work`:** full suite green. The WS fan-out + downsampling + anonymization tests are load-bearing; the chart-not-blank smoke test is the react-is-override sentinel.
- **Max feedback latency:** ~90s (full backend suite with Redis integration).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | MKT-04 | T-09-02 | WS payload is the lean delta only — no `_latency_ms`/PII | integration (scaffold) | `cd backend && uv run pytest tests/realtime/ --collect-only -q` | ❌ W0 | ⬜ pending |
| 09-01-02 | 01 | 1 | MKT-04 | T-09-01 / T-09-04 | Public WS, subscriber cancelled on shutdown, ping→pong only | integration | `cd backend && uv run pytest tests/realtime/test_ws_fanout.py tests/realtime/test_ws_isolation.py tests/realtime/test_ws_reconnect.py -x` | ❌ W0 | ⬜ pending |
| 09-01-03 | 01 | 1 | MKT-04 | T-09-03 | Publish post-commit only (admin edit) + on-change only (poll) | integration | `cd backend && uv run pytest tests/markets/test_update_market_publishes.py tests/polymarket/test_poll_publishes.py -x` | ❌ W0 | ⬜ pending |
| 09-02-01 | 02 | 2 | MKT-03 | T-09-05 / T-09-06 | Activity schema has no user field; money/odds as strings | unit | `cd backend && uv run pytest tests/markets/test_price_history.py tests/markets/test_activity_feed.py -x -m "not integration"` | ❌ W0 | ⬜ pending |
| 09-02-02 | 02 | 2 | MKT-03 | T-09-07 / T-09-08 | 30d downsampled server-side; window allowlist; no user-id key | integration | `cd backend && uv run pytest tests/markets/test_price_history.py tests/markets/test_activity_feed.py -x` | ❌ W0 | ⬜ pending |
| 09-03-01 | 03 | 2 | MKT-03/04 | T-09-SC | Package legitimacy gate (blocking human) before install | manual gate | (checkpoint — human verify, no automated cmd) | N/A | ⬜ pending |
| 09-03-02 | 03 | 2 | MKT-03/04 | T-09-SC | Single react-is version (override); clean build | smoke | `cd frontend && pnpm why react-is && pnpm build` | ✅ (build) | ⬜ pending |
| 09-03-03 | 03 | 2 | MKT-03 | — | Chart renders SVG (not blank) — react-is sentinel | unit (frontend) | `cd frontend && pnpm test src/components/price-history-chart.test.tsx` | ❌ W0 | ⬜ pending |
| 09-03-04 | 03 | 2 | MKT-04 | T-09-09 / T-09-11 | >30s silence → Stale, odds kept visible; backoff reconnect | unit (frontend) | `cd frontend && pnpm test src/hooks/use-market-socket.test.ts` | ❌ W0 | ⬜ pending |
| 09-04-01 | 04 | 3 | MKT-03 | T-09-12 / T-09-13 | Each backend status → specific inline copy; cookie-forward; no bypass | unit (frontend) | `cd frontend && pnpm test src/components/order-entry-form.test.tsx` | ❌ W0 | ⬜ pending |
| 09-04-02 | 04 | 3 | MKT-03 | T-09-14 | Activity feed renders no user identity; SSR shell + skeletons | build + render | `cd frontend && pnpm build && pnpm test` | ✅ (build) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Created as RED scaffolds in their owning plans (Task 1 of each backend plan; the test file alongside each frontend component):

- [ ] `backend/tests/realtime/__init__.py` + `conftest.py` — WS test client (`websockets`) + real-redis pub/sub fixture (09-01 Task 1)
- [ ] `backend/tests/realtime/test_ws_fanout.py` — MKT-04 publish→broadcast <2s (09-01 Task 1)
- [ ] `backend/tests/realtime/test_ws_isolation.py` — MKT-04 per-market isolation (09-01 Task 1)
- [ ] `backend/tests/realtime/test_ws_reconnect.py` — MKT-04 reconnect receives new deltas (09-01 Task 1)
- [ ] `backend/tests/markets/test_update_market_publishes.py` — producer hook #1 (admin edit, post-commit) (09-01 Task 3)
- [ ] `backend/tests/polymarket/test_poll_publishes.py` — producer hook #2 (poll on change) (09-01 Task 3)
- [ ] `backend/tests/markets/test_price_history.py` — price-history endpoint + 30d downsample (+ 30-day backfill fixture) (09-02 Tasks 1-2)
- [ ] `backend/tests/markets/test_activity_feed.py` — anonymized last-20 (negative: no user identity) (09-02 Tasks 1-2)
- [ ] `frontend/src/components/price-history-chart.test.tsx` — chart-not-blank smoke (react-is sentinel) (09-03 Task 3)
- [ ] `frontend/src/hooks/use-market-socket.test.ts` — connection state machine (fake timers) (09-03 Task 4)
- [ ] `frontend/src/components/order-entry-form.test.tsx` — backend-status → inline-copy mapping (09-04 Task 1)
- [ ] Confirm `websockets` is available as a backend test-only client (ships with `fastapi[standard]`; else `uv add --dev websockets`).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Full MKT-04 round-trip on a live page (admin odds edit / Polymarket poll → odds animate on /markets/{slug} within 2s) | MKT-04 | Requires the full stack running (uvicorn + Celery beat + Redis + Next dev) + a browser; the automated WS tests cover the pipeline in isolation but not the end-to-end browser render | Run `bin/dev` (or docker compose); open `/markets/{slug}`; in another tab PATCH the market's `odds_yes` via the admin API; confirm the YES % updates in place + the Live dot pulses within 2s |
| Recharts renders a real emerald line in a browser (not just jsdom) | MKT-03 | jsdom does not paint SVG; the smoke test asserts a `path` element exists but a human confirms the visual line | Open `/markets/{slug}` with ≥2 snapshots; confirm an emerald YES line renders across the chart area |
| Package legitimacy (09-03 Task 1) | MKT-03/04 | Blocking human checkpoint — verify the four npm packages before install | See 09-03 Task 1 `<how-to-verify>` |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (the one non-automated task is the 09-03 Task 1 blocking checkpoint, which is a human gate by design)
- [x] Sampling continuity: no 3 consecutive code tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags (frontend uses `pnpm test` = `vitest run`)
- [x] Feedback latency < 90s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-05-29
