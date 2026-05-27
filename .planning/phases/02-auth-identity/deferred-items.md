# Phase 2 — Deferred Items (out-of-scope discoveries)

## Pre-existing Phase 1 test isolation bug

**Discovered:** During Plan 02-01 Task 3 verification (full backend `pytest` run).

**Symptom:** When `pytest` runs the whole `backend/tests/` tree, 6 Phase 1
integration tests in `tests/core/test_feature_flags.py` and
`tests/core/test_audit_immutability.py` fail because earlier tests in the
same file mutate state (`UPDATE feature_flags SET enabled = TRUE`, or raise
a DBAPIError that aborts the shared transaction) and the session-scoped
`async_session` fixture (`tests/conftest.py` lines 174-198) does NOT
isolate state between tests within a session.

**Reproduction (at parent commit `dd588e7`):** `cd backend && uv run pytest
tests/core/test_feature_flags.py` — 4 pass, 1 fails (`test_tenant_fallback`).

**Why this didn't surface in Phase 1 acceptance:** Likely Phase 1 ran each
integration file in isolation or in an order that didn't expose the
mutation. The Phase 1 SUMMARY recorded 39/39 green; this issue likely
emerges only under the alphabetic full-suite ordering pytest defaults to.

**Why NOT auto-fixing in 02-01:** Per the SCOPE BOUNDARY in
`execute-plan.md` deviation rules: "Only auto-fix issues DIRECTLY caused
by the current task's changes." Test 02-01 changes do not touch
`tests/core/*`, `app/core/feature_flags/*`, or `app/core/audit/*` — the
failures predate this plan.

**Recommended fix (Phase 8 or earlier, owner TBD):** Convert
`async_session` to function-scoped with a `begin_nested()` savepoint, or
add per-test cleanup in `tests/core/test_*` files. The PATTERNS.md
"Integration Test Pattern" (lines 796-805) implies function-scoped
isolation; the current implementation in `conftest.py` (`scope="session"`)
contradicts this. Worth re-reading the Phase 1 SUMMARY decisions on this
before changing.

**Phase 2 mitigation:** Phase 2 auth integration tests run their own
inserts and either explicitly clean up (e.g. `test_users_tenant_id_default`
issues a `DELETE … WHERE email = 'tenantdefault-test@example.com'`) or
use sufficiently unique data that intra-session collisions are unlikely.
