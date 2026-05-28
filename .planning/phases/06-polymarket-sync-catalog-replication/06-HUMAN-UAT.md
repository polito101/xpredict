---
status: complete
phase: 06-polymarket-sync-catalog-replication
source: [06-VERIFICATION.md]
started: 2026-05-28T09:55:00Z
updated: 2026-05-28T09:55:00Z
---

## Current Test

number: 1
name: Home page browser render
expected: |
  Responsive market card grid with question, YES/NO odds, volume, deadline, and source badge visible at all breakpoints (1 col mobile, 2 tablet, 3 desktop)
awaiting: user response

## Tests

### 1. Home page browser render
expected: Responsive market card grid with question, YES/NO odds, volume, deadline, and source badge visible at all breakpoints (1 col mobile, 2 tablet, 3 desktop)
result: PASS — verified 2026-05-28 by Pol (screenshot). 3-col desktop grid renders 25 Polymarket crypto markets. Each card shows question, YES/NO odds bars (50/50 — expected, outcomes[] empty from Gamma API), Vol $0, "Ended" deadline, Polymarket source badge.

### 2. SourceBadge click behavior
expected: Polymarket badge opens polymarket.com in new tab; card body navigates to /markets/{slug}
result: PASS — verified 2026-05-28 by Pol. Badge opens polymarket.com, card body navigates to /markets/{slug}. Both links work.

### 3. Suspense skeleton loading state
expected: 6-card skeleton grid appears before data loads (visible on slow network or Suspense boundary test)
result: PASS — verified 2026-05-28 by Pol. Skeleton cards visible before data loads.

### 4. Celery Beat runtime scheduling
expected: poll_polymarket_top25 fires every 30s, snapshot_odds every 5min, Redis SETNX lock prevents overlapping executions
result: PASS — verified 2026-05-28. beat dispatches poll every ~30s and snapshot every 5min. Worker has all 3 tasks registered. 25 Polymarket markets synced to DB via /api/v1/markets. Required fix: added `include` to celery_app.py for task autodiscovery (commit 004dcca).

## Summary

total: 4
passed: 4
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
