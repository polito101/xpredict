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

## Cross-worktree gitleaks history scan picks up sibling commits

**Discovered:** During Plan 02-03 final verification (`uv run pytest tests/`).

**Symptom:** `tests/test_gitleaks_blocks_secret.py::test_gitleaks_clean_scan_of_full_repo`
fails with 23 leaks. Inspecting the JSON report shows ALL the leaks
come from commit `54af9454…` on a sibling worktree branch (the 02-04
frontend worktree-agent, running in parallel) — files like
`frontend/src/lib/__tests__/auth.test.ts` introduce test passwords
(`"Valid-Pass-1234"`) that gitleaks' `generic-api-key` rule flags.

**Why this is out-of-scope for 02-03:** The commit is NOT in the 02-03
worktree branch (`git log --all --oneline | grep 54af9454` shows it
exists, but `git log --oneline -5` on `worktree-agent-…` does not have
it). The leak files are frontend-only (`frontend/src/lib/__tests__/`)
and 02-03 does not touch the frontend.

**Root cause:** gitleaks `detect` operates on the **shared git history**
of the repository, not the worktree's working tree. Worktrees share the
same `.git/` directory, so a commit landed by ANY worktree is visible
to ALL worktrees' `gitleaks detect` runs.

**Recommended fix (owner 02-04 or Phase 11 hardening):**
- Either extend `.gitleaks.toml` `[allowlist].paths` with
  `frontend/src/lib/__tests__/.*` (mirror of the existing
  `tests/.*fixtures.*` allowlist for backend test data — Plan 01-04
  D-46 patterns), OR
- Change test fixtures in `frontend/src/lib/__tests__/auth.test.ts` to
  use a clearly non-secret form (`"Valid-Pass-1234"` has high entropy
  and triggers the generic-api-key heuristic; using a clearly-marked
  fixture like `"FIXTURE_PASSWORD_NOT_REAL"` would pass the entropy
  threshold).

**Phase 2 Wave 3 status:** Other 7 pre-existing test failures
(`tests/core/test_audit_immutability.py` + `tests/core/test_feature_flags.py`)
are the unchanged Phase 1 isolation bug above; plus the new
`test_gitleaks_clean_scan_of_full_repo` failure documented here. Total:
8 pre-existing failures, 0 introduced by Plan 02-03. Plan 02-03's own
test surface (`tests/auth/`) is 74/74 green.
