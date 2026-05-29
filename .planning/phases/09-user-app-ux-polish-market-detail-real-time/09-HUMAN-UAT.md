---
status: partial
phase: 09-user-app-ux-polish-market-detail-real-time
source: [09-VERIFICATION.md]
started: 2026-05-29
updated: 2026-05-29
---

## Current Test

[awaiting human testing — requires a running stack + browser]

## Tests

### 1. Full MKT-04 real-time round-trip (browser)
expected: With the full stack running (`bin/dev` or docker compose: uvicorn + Celery beat + Redis + Next.js dev), open `/markets/{slug}`. In another tab, PATCH the market's `odds_yes` via the admin API (or wait for a Polymarket poll on a mirrored market). The YES % updates IN PLACE on the open detail page within ~2s with no page refresh, and the "Live" dot pulses. After >30s of silence, the badge flips to amber "Stale" while the last-known odds stay visible.
result: [pending]

### 2. Recharts YES line renders visually (browser)
expected: Open `/markets/{slug}` for a market with ≥2 `OddsSnapshot` rows. An emerald (#059669) YES-probability line renders across the chart area (NOT a blank box) — confirms the `react-is@19.2.6` pnpm override is effective in a real browser. Toggle 24h / 7d / 30d and confirm the series re-renders. A market with <2 snapshots shows the friendly "Not enough price history yet" empty state.
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps

<!-- Automated coverage (all VERIFIED): producer→Redis→subscriber→WS-client pipeline (tests/realtime/), price-history downsampling + window allowlist, activity anonymization (negative test), chart-not-blank SVG-path smoke test, order-form backend-status→inline-error mapping, build green. These 2 items are the browser-only residue that no headless test can cover. -->
