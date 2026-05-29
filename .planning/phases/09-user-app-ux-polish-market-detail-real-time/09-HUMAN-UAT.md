---
status: passed
phase: 09-user-app-ux-polish-market-detail-real-time
source: [09-VERIFICATION.md]
started: 2026-05-29
updated: 2026-05-29
validated_by: live stack (docker Postgres+Redis + host uvicorn + Next dev) + headless browser
---

## Current Test

Complete — both browser-only items validated against a running stack on 2026-05-29.

## Tests

### 1. Full MKT-04 real-time round-trip (browser)
expected: an odds change propagates to the open `/markets/{slug}` page within ~2s, in place, no refresh; the indicator reflects Live/Stale.
result: **PASS** — In a headless browser on the live `/markets/{slug}` page, publishing an odds-change delta drove the page from **YES 62% / NO 38% → YES 77% / NO 23%** in place with no refresh, and the connection indicator flipped **"Stale" → "Live"**. Backend pipeline latency measured separately at **mean 5.4ms / max 13.7ms over 5 rounds (≪ 2s)** via a WS client + Redis publish. The earlier "Stale" was the correct idle state (>30s without an update keeps the last odds + shows the amber badge).

### 2. Recharts YES line renders visually (browser)
expected: an emerald YES-probability line renders (not blank) for a market with ≥2 snapshots; window toggles re-render; <2-snapshot markets show the empty state.
result: **PASS** — The detail page renders a real emerald YES line (screenshot captured; `.recharts-line-curve` + `.recharts-surface` present in the live DOM). Verified on a **POLYMARKET market with title-case "Yes"/"No" outcomes**, which doubly confirms (a) the `react-is@19.2.6` pnpm override is effective on React 19 (chart not blank) and (b) the **IN-01 fix** (case-insensitive YES selection) — the chart has data for a Polymarket market. The 30d / 24h window toggles re-render the line client-side (apiBase() client path).

## Summary

total: 2
passed: 2
issues: 0
pending: 0
skipped: 0
blocked: 0

## Validation evidence (closeout 2026-05-29)

Stack: docker `db` (Postgres 16, :5432) + `redis` (:6379), Alembic migrated to head (0001→0007), backend `uvicorn` on host (:8000), Next dev (:3000). Seed: 2 markets (HOUSE `YES/NO` + POLYMARKET `Yes/No`) × ~54 OddsSnapshots over 30d.

Live-validated beyond the 2 items above:
- **Realtime fan-out + latency:** WS client ↔ `/ws/markets/{id}` + Redis publish → mean 5.4ms / max 13.7ms (5 rounds); payload = lean delta, no PII.
- **CR-01 WS abuse controls:** disallowed `Origin` → handshake **403**; injection-charset `market_id` → **400**; safe ids accepted (no DB lookup, capped). Connection cap covered by `tests/realtime/test_connection_cap.py`.
- **price-history endpoint:** 24h/7d/30d return points; **30d downsampled** server-side (hourly buckets); `probability` is a JSON **string**; **IN-01 live** — the POLYMARKET "Yes" market returns a non-empty series (24h=15, 7d=23, 30d=53).
- **window allowlist** → `?window=99h` = **422**; unknown slug = **404** (the "Market not found" state renders with a Back-to-markets link).
- **activity** endpoint anonymized (no user-identity keys); empty state ("No bets yet") renders.
- **SSR + UI-SPEC fixes:** detail page server-renders the question, always-visible resolution criteria, "Order entry" panel (UI-audit fix), Recent activity, Live indicator.

Fixed during closeout (committed on the phase branch):
- **NEXT_PUBLIC URL wiring (`7c2ee32`)** — under the all-docker `bin/dev` flow the browser bundle baked `…backend:8000` (unresolvable from a host browser), silently breaking the WS + client chart re-fetch. `lib/api.ts apiBase()` now splits SSR (`BACKEND_URL`) vs browser (`NEXT_PUBLIC_API_URL`); docker-compose sets `NEXT_PUBLIC_*=localhost`. Re-verified live (SSR + client toggles + realtime).

Notes (non-blocking):
- **Recharts `width(-1)/height(-1)` console warning** — benign environment/initial-measure artifact; also appears under jsdom (no layout). The chart's parent is correctly `h-64` per UI-SPEC and the line renders in a real browser. Left as-is (no change to working chart code); recommended future one-liner: pass `minHeight` to `ResponsiveContainer`.
- **Bet modal + inline errors** — the form is correctly **auth-gated** (logged-out users see no Place-bet button, verified live in SSR), and the full backend-status → inline-copy mapping is **unit-tested 7/7** (`order-entry-form.test.tsx`: 402/409/403/422/401 + success). The interactive modal was not driven live (would require a verified player + balance + mailpit email infra — out of proportion to the existing deterministic coverage).
- **DEF-FE-01** orphan (`middleware.test.ts`) remains the only repo-wide red `tsc`/`pnpm test` — pre-existing on `main`, tracked separately (spawned task).
