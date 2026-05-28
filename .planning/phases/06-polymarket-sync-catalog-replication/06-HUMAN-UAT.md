---
status: partial
phase: 06-polymarket-sync-catalog-replication
source: [06-VERIFICATION.md]
started: 2026-05-28T09:55:00Z
updated: 2026-05-28T09:55:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Home page browser render
expected: Responsive market card grid with question, YES/NO odds, volume, deadline, and source badge visible at all breakpoints (1 col mobile, 2 tablet, 3 desktop)
result: [pending]

### 2. SourceBadge click behavior
expected: Polymarket badge opens polymarket.com in new tab; card body navigates to /markets/{slug}
result: [pending]

### 3. Suspense skeleton loading state
expected: 6-card skeleton grid appears before data loads (visible on slow network or Suspense boundary test)
result: [pending]

### 4. Celery Beat runtime scheduling
expected: poll_polymarket_top25 fires every 30s, snapshot_odds every 5min, Redis SETNX lock prevents overlapping executions
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
