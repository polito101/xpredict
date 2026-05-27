---
status: partial
phase: 02-auth-identity
source: [02-VERIFICATION.md]
started: 2026-05-27T00:00:00Z
updated: 2026-05-27T00:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Player registration end-to-end
expected: Full email round-trip via Mailpit + xpredict_session cookie visible in browser DevTools after login
result: [pending]

### 2. Forgot-password enumeration safety (UI)
expected: Identical rendered message for known vs. unknown email; no visual or timing side-channel detectable in browser
result: [pending]

### 3. Admin login and /admin/ access guard
expected: Edge middleware redirects unauthenticated /admin/* requests to /admin/login; after login, admin_jwt cookie scoped to path=/admin visible in DevTools
result: [pending]

### 4. Rate-limit 429 in live stack
expected: Redis-backed slowapi returns 429 with generic message after rate limit exceeded (unit tests use memory:// — needs live Redis confirmation)
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
