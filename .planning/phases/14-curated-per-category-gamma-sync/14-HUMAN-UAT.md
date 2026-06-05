---
status: partial
phase: 14-curated-per-category-gamma-sync
source: [14-VERIFICATION.md]
started: 2026-06-05
updated: 2026-06-05
---

## Current Test

[awaiting human testing — both items are POST-DEPLOY; not verifiable in the dev worktree pre-merge]

## Tests

### 1. redbeat schedule reload after deploy
expected: After the PR merges and the stack is deployed/restarted, the **beat process is restarted** so redbeat re-syncs the schedule from Redis. Then: `poll_polymarket_events` fires every 300s (logs `poll_events.category_synced`), `poll_polymarket_top25` no longer fires, and `market_groups` rows + grouped children appear in the DB. (Code-side swap already verified green by `test_beat_schedule_entries`; only the live reload is manual.)
result: [pending]

### 2. Live tag_id drift re-verify at deploy
expected: At deploy start, run the 7-slug check and confirm the pinned ids are unchanged:
```
for slug in politics sports crypto pop-culture economy tech world; do
  curl -s "https://gamma-api.polymarket.com/tags/slug/$slug" | python -c "import sys,json;t=json.load(sys.stdin);print(t['slug'],t['id'])"
done
```
Expected: politics=2, sports=1, crypto=21, pop-culture=596, economy=100328, tech=1401, world=101970. A drifted id would silently mis-route or empty a category.
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps

None — these are runtime/external verifications by design (VALIDATION.md › Manual-Only), not code gaps. The implementation is complete and the phase goal is verified in code (11/11 must-haves).
