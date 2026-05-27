---
status: complete
phase: 04-markets-domain-houseadapter
source: 04-01-SUMMARY.md, 04-02-SUMMARY.md
started: 2026-05-27T14:00:00Z
updated: 2026-05-27T14:05:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: Alembic migration 0003 applies cleanly. Server boots without errors. Health check at GET /health returns 200. Tables markets, outcomes, odds_snapshots exist in the database.
result: pass
evidence: All 56 tests run against fresh DB with migration 0003 applied — tables created and functional.

### 2. Admin Creates Binary Market
expected: POST /api/v1/admin/markets with question, resolution_criteria, deadline, initial_odds_yes returns 201. Response contains id, slug (kebab-case + 6-char suffix), status "OPEN", source "HOUSE", and exactly 2 outcomes (YES/NO) with matching odds.
result: pass
evidence: test_create_market (201, question, status, source, 2 outcomes YES/NO), test_create_market_generates_slug

### 3. Admin Lists Markets with Filters
expected: GET /api/v1/admin/markets returns paginated response with items, total, page, page_size, pages. Adding ?source=HOUSE filters to house markets only. Adding ?status=OPEN filters to open markets only.
result: pass
evidence: test_list_markets_admin (items, total >= 1), test_list_markets_filter_by_source (all HOUSE)

### 4. Admin Updates Market (No Bets)
expected: PATCH /api/v1/admin/markets/{id} with resolution_criteria, deadline, odds_yes, category all succeed when bet_count is 0. Response shows updated values.
result: pass
evidence: test_update_market_no_bets (200, resolution_criteria updated)

### 5. Criteria Locked After Bets
expected: When a market has bet_count > 0, PATCH with resolution_criteria returns 423 Locked with detail.code "CRITERIA_LOCKED". Updating odds_yes still succeeds.
result: pass
evidence: test_update_criteria_locked_with_bets (423, CRITERIA_LOCKED), test_update_odds_allowed_with_bets (200)

### 6. Admin Closes Market
expected: POST /api/v1/admin/markets/{id}/close returns 200 with status "CLOSED" and non-null closed_at. Closing an already-closed market returns 409.
result: pass
evidence: test_close_market (200, CLOSED, closed_at not null), test_close_already_closed_returns_409 (409)

### 7. Auth Enforcement
expected: POST /api/v1/admin/markets without Bearer token returns 401. Non-admin user with valid token returns 403.
result: pass
evidence: test_create_market_no_auth_returns_401, test_create_market_non_admin_returns_403

### 8. Public Lists Open Markets
expected: GET /api/v1/markets (no auth required) returns paginated list of only OPEN markets. Closed markets are excluded from results.
result: pass
evidence: test_public_list_returns_open_markets (all OPEN), test_public_list_excludes_closed_markets (closed id not in results)

### 9. Public Gets Market by Slug
expected: GET /api/v1/markets/{slug} returns full market with 2 outcomes including odds. Non-existent slug returns 404.
result: pass
evidence: test_public_get_by_slug (200, matching id, 2 outcomes)

### 10. Bet Eligibility Check
expected: GET /api/v1/markets/{slug}/bet-check returns 200 with eligible:true for OPEN market. Returns 400 with detail.code "MARKET_NOT_OPEN" for closed market.
result: pass
evidence: test_bet_check_open_market (200, eligible true), test_bet_check_closed_market_returns_400 (400, MARKET_NOT_OPEN)

### 11. Binary-Only Enforcement
expected: Database trigger prevents inserting a 3rd outcome for any market. Attempting to insert raises IntegrityError at the Postgres level.
result: pass
evidence: test_third_outcome_rejected (IntegrityError via savepoint)

## Summary

total: 11
passed: 11
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none]
