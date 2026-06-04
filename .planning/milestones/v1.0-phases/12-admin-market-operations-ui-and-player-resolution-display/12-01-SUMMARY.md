---
phase: 12-admin-market-operations-ui-and-player-resolution-display
plan: 01
subsystem: database
tags: [alembic, sqlalchemy, postgres, settlement, markets, pydantic, decimal]

# Dependency graph
requires:
  - phase: 04-markets-domain
    provides: Market/Outcome models, get_market_public, MarketRead/Create/Update schemas
  - phase: 05-bets-settlement
    provides: SettlementService.resolve_market, MarketResolvePort, HouseMarketResolveAdapter, the ACID settlement transaction
  - phase: 10-admin-dashboard-branding
    provides: migration head 0009_phase10_tenant_config (the down_revision this chains off)
provides:
  - "markets.winning_outcome_id / resolution_source / resolution_justification persisted INSIDE the settlement ACID transaction (STL-06 data layer)"
  - "GET /api/v1/markets/{slug} returns 200 for RESOLVED markets; MarketRead carries the 4 resolution fields"
  - "markets.min_stake / max_stake nullable columns for per-market BET-06 stake limits (NULL = global default)"
  - "Migration 0010 applied to the project Postgres (alembic current == 0010_phase12_resolution_stakes)"
affects: [12-02 (per-market stake enforcement), 12-03 (admin resolve/reverse UI), 12-04 (player resolved-panel display)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Atomic resolution projection: the winner/source/justification are written on the settlement session by mark_resolved (no separate commit) so they commit all-or-nothing with the payouts + audit row"
    - "resolution_source stored as a stable token (HOUSE / POLYMARKET_UMA) derived from actor_user_id — a denormalized, publicly-readable projection of the audit-log resolver"
    - "Per-market money limits use the documented nullable-money exception (Mapped[Decimal | None] + Numeric(18,4)), NOT Mapped[Money] (which is NOT-NULL)"
    - "Alembic revision id decoupled from the descriptive filename to fit the varchar(32) alembic_version.version_num"

key-files:
  created:
    - backend/alembic/versions/0010_phase12_resolution_and_stake_limits.py
  modified:
    - backend/app/markets/models.py
    - backend/app/markets/schemas.py
    - backend/app/markets/router.py
    - backend/app/settlement/market_port.py
    - backend/app/settlement/adapters.py
    - backend/app/settlement/service.py
    - backend/tests/settlement/test_settlement_router.py
    - backend/tests/settlement/test_resolve_market.py
    - backend/tests/settlement/test_force_settle.py
    - backend/tests/settlement/test_market_resolve_port.py
    - backend/tests/admin/test_kpi.py
    - backend/tests/markets/test_public_router.py

key-decisions:
  - "BET-06 storage diverges from the requirement wording: nullable min_stake/max_stake columns ON markets, NOT TenantConfig (a single-row global table structurally unfit for per-market values). Global BET_MIN/MAX_STAKE config constants kept as the default."
  - "resolution_source is a stable token (HOUSE when actor_user_id set, POLYMARKET_UMA when None) — the player-facing 'Operator: {name}' display name is resolved in the frontend slice (12-04); this plan stores the token only."
  - "No backfill of pre-Phase-12 RESOLVED markets — keeps the migration purely additive + reversible (demo runs on a fresh/seeded DB). A follow-up backfill can read audit_log.payload.winning_outcome if Pol wants historical markets to render fully."
  - "Migration 0010 revision id shortened to 0010_phase12_resolution_stakes (30 chars) — alembic_version.version_num is varchar(32); the 40-char descriptive name failed to apply. Filename keeps the descriptive form."

patterns-established:
  - "Resolution-column persist ripple: a single Protocol signature change (mark_resolved + resolution_source + justification) propagated in lockstep to the real adapter, the service call site, and all 6 test fakes + the @runtime_checkable conformance test — a partial edit breaks mypy/runtime conformance."

requirements-completed: [STL-06, BET-06]

# Metrics
duration: ~30min
completed: 2026-06-03
---

# Phase 12 Plan 01: Resolution Winner Persistence & Stake-Limit Columns Summary

**Persists the resolution winner + source + justification on the markets row inside the existing settlement ACID transaction (STL-06 root-cause fix) and adds nullable per-market min/max_stake columns (BET-06 storage), with get_market_public now returning 200 for RESOLVED markets — applied live via migration 0010.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-06-03 (phase execution session)
- **Completed:** 2026-06-03T16:01Z
- **Tasks:** 3 (2 code tasks + 1 blocking apply task)
- **Files modified:** 13 backend files (1 created, 12 modified)

## Accomplishments
- **STL-06 data layer fixed:** `HouseMarketResolveAdapter.mark_resolved` now persists `winning_outcome_id`, `resolution_source`, and `resolution_justification` on the markets row on the settlement session — previously the winner lived ONLY in the admin-gated audit log, so the player saw no winner.
- **STL-06 read surface fixed:** `get_market_public` returns 200 (was 404) for RESOLVED markets; `MarketRead` exposes the 4 resolution fields (winner/source/justification/resolved_at) and the 2 stake fields, money serialized as JSON string-or-None.
- **BET-06 storage landed:** nullable `markets.min_stake` / `markets.max_stake` (Numeric(18,4)) added for per-market limits; the global config defaults remain the fallback.
- **Atomicity preserved:** the ledger transfer specs, FOR UPDATE lock ordering, and the `AuditService.record` block in `resolve_market` are byte-unchanged — resolution stays all-or-nothing and idempotent.
- **Migration applied to a real project Postgres** (not faked): `alembic current` == `0010_phase12_resolution_stakes`, all 5 columns verified queryable on the live `markets` table.

## Task Commits

Each task was committed atomically:

1. **Task 1: Migration 0010 + Market model + market schemas** — `f5ef989` (feat)
2. **Task 2: Atomic mark_resolved ripple (Protocol + adapter + service + 6 fakes) + get_market_public RESOLVED** — `fd2212c` (feat) — includes the Rule-1 revision-id fix
3. **Task 3: [BLOCKING] Apply migration 0010 to the running DB** — no code change (operational apply step; the migration file was committed in Tasks 1/2). Applied live + verified.

**Plan metadata:** (final docs commit — see below)

_Note: Tasks 1 & 2 are marked tdd="true". They are additive schema/Protocol changes where the test surface and implementation are inseparable (the migration must exist before any test imports the new columns, and the Protocol signature must change in lockstep with all 6 fakes). The RED/GREEN gate here is the verification suite: alembic-heads + mypy + money-lint + the 6-fake conformance + the new RESOLVED-200/persist assertions all fail without the change and pass with it._

## Files Created/Modified
- `backend/alembic/versions/0010_phase12_resolution_and_stake_limits.py` — **created.** Additive migration: 5 nullable columns on `markets`; `down_revision = "0009_phase10_tenant_config"`, single linear head. `revision = "0010_phase12_resolution_stakes"` (filename keeps the long descriptive form).
- `backend/app/markets/models.py` — added the 5 columns to `Market` (resolution trio + stake pair); imported `Numeric`. Stake columns use the nullable-money exception.
- `backend/app/markets/schemas.py` — `MarketRead` gains the 3 resolution fields + min/max_stake (with a None-guarding `serialize_stake_decimal` field_serializer); `MarketCreate`/`MarketUpdate` gain optional `min_stake`/`max_stake` (ge=0).
- `backend/app/markets/router.py` — `get_market_public` now allows `MarketStatus.RESOLVED` (returns 200).
- `backend/app/settlement/market_port.py` — `MarketResolvePort.mark_resolved` signature extended with `resolution_source` + `justification`; docstring updated.
- `backend/app/settlement/adapters.py` — `HouseMarketResolveAdapter.mark_resolved` persists the 3 resolution fields on the caller's session (no commit).
- `backend/app/settlement/service.py` — `resolve_market` derives `resolution_source` ("POLYMARKET_UMA" if `actor_user_id is None` else "HOUSE") and passes it + `justification` through. Ledger math + audit block unchanged.
- `backend/tests/settlement/test_settlement_router.py`, `test_resolve_market.py` (2 fakes), `test_force_settle.py`, `test_market_resolve_port.py`, `backend/tests/admin/test_kpi.py` — all 6 `mark_resolved` fakes updated to the new signature.
- `backend/tests/settlement/test_resolve_market.py` — **new tests:** persist-assertion via the REAL `HouseMarketResolveAdapter` against a real seeded markets row, for both the HOUSE (actor set) and POLYMARKET_UMA (actor None) paths.
- `backend/tests/markets/test_public_router.py` — **new test:** RESOLVED market returns 200 with `winning_outcome_id`/`resolution_source`/`resolution_justification`/`resolved_at` present in the body.

## Decisions Made
- **BET-06 columns vs TenantConfig (surfaced for Pol).** REQUIREMENTS/ROADMAP say per-market limits "via TenantConfig"; `TenantConfig` is a verified SINGLE-ROW global table (`UNIQUE(tenant_id)`), structurally unfit for per-MARKET values. Per RESEARCH A1 + PATTERNS, stored as nullable `min_stake`/`max_stake` ON `markets` (NULL = the global `BET_MIN_STAKE`/`BET_MAX_STAKE` config default). The global constants are NOT removed. This is the one place the build diverges from the requirement wording, on evidence.
- **resolution_source token choice.** Stored as a stable token derived from `actor_user_id` (None => POLYMARKET_UMA / auto path; set => HOUSE / admin path). The audit row already records the resolver UUID; the column is a denormalized, publicly-readable projection. The player-facing "Operator: {name}" display name is resolved in the frontend slice (12-04).
- **No backfill.** Pre-Phase-12 RESOLVED markets keep their audit-log-only winner (would show a degraded panel). The migration stays purely additive + reversible; a follow-up backfill task can read `audit_log.payload.winning_outcome` if Pol wants historical markets to render fully. Flagged, not silently attempted.
- **Migration-apply outcome: APPLIED (not host-gated).** Brought up the compose `db` service (`docker compose up -d db`, host port 5432 free — crypto-casino's `cc_postgres` is on 5433) and ran `alembic upgrade head` against it with the dev `xpredict:xpredict` credentials + throwaway `SECRET_KEY`/`ADMIN_JWT_PUBLIC_SECRET` (needed only to satisfy `Settings()` validation; they never touch the DB). `alembic current` == `0010_phase12_resolution_stakes`; all 5 columns verified on the live `markets` table. The `xpredict-db-1` container is left running (correctly migrated to head — useful for plans 12-02..12-06).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Migration revision id too long for `alembic_version.version_num` (varchar(32))**
- **Found during:** Task 2 (first integration-suite run, when `alembic upgrade head` ran against the testcontainer)
- **Issue:** The plan specified `revision = "0010_phase12_resolution_and_stake_limits"` (40 chars). The `alembic_version.version_num` column is `varchar(32)`, so applying the migration failed with `psycopg2.errors.StringDataRightTruncation` on the `UPDATE alembic_version SET version_num=...` statement. The migration FILE passed `alembic heads` (which reads the Python files, not the DB), masking the defect until the DB apply. This is a genuine data-layer bug in the planned revision id.
- **Fix:** Shortened the in-table `revision` id to `0010_phase12_resolution_stakes` (30 chars, fits varchar(32)). Kept the descriptive FILENAME `0010_phase12_resolution_and_stake_limits.py` (alembic decouples the filename from the revision id — only the id strings govern the version table). Added a NOTE in the migration docstring explaining why. `down_revision = "0009_phase10_tenant_config"` (26 chars) was unaffected.
- **Files modified:** `backend/alembic/versions/0010_phase12_resolution_and_stake_limits.py`
- **Verification:** `alembic heads` → single head `0010_phase12_resolution_stakes`; the full integration suite then applied the migration cleanly (62 → 184 tests green); `alembic upgrade head` + `alembic current` against the project Postgres confirmed the apply.
- **Committed in:** `fd2212c` (Task 2 commit)

**Note on the plan's must_haves/acceptance literals:** the plan's `must_haves.artifacts` and Task-1 acceptance criteria reference the revision id `0010_phase12_resolution_and_stake_limits`. The artifact PATH (the filename) is satisfied verbatim; the in-table id is the shortened form for the documented varchar(32) reason. The `down_revision`/`contains` literal `0009_phase10_tenant_config` is preserved exactly.

---

**Total deviations:** 1 auto-fixed (1 Rule-1 bug)
**Impact on plan:** The fix was required for the migration to physically apply — without it, Task 3 (the BLOCKING apply) is impossible and CI would red on every migration run. No scope creep; the descriptive filename and all other plan literals are preserved.

## Issues Encountered
- **`Settings()` requires env vars for ad-hoc CLI alembic.** There is no committed `.env` (secrets stay out of the repo per project convention), so a bare `uv run alembic current` from the host shell fails `Settings()` validation (`SECRET_KEY`, `ADMIN_JWT_PUBLIC_SECRET` missing). Resolved by passing the dev compose DB URL + throwaway secrets inline for the apply/verify commands (the secrets are validation-only and never reach the DB). This mirrors how the compose stack injects env via the `x-backend-env` anchor inside the container.

## Known Stubs
None — every change is real wiring (persisted columns, exposed schema fields, the relaxed public guard). No placeholder/empty-data stubs introduced (diff scan clean).

## User Setup Required
None — no external service configuration required. The migration is already applied to the local project Postgres; for any fresh environment, `alembic upgrade head` (the compose stack provides the env) brings the columns into existence. CI (testcontainers) applies it green automatically.

## Next Phase Readiness
- **STL-06 backend foundation complete** — plans 12-03 (admin resolve/reverse UI) and 12-04 (player resolved-panel display) can now read `winning_outcome_id`/`resolution_source`/`resolution_justification` off `MarketRead` for any RESOLVED market via the public endpoint.
- **BET-06 storage ready** — plan 12-02 (per-market stake enforcement) can read/write `markets.min_stake`/`max_stake`; the `MarketCreate`/`MarketUpdate` schemas already accept them. NULL-means-global-default semantics are the enforcement contract.
- **Open flag for Pol:** the BET-06 columns-vs-TenantConfig divergence and the no-backfill decision are both surfaced above for plan-review acknowledgement.

## Self-Check: PASSED

- All created/modified files verified present on disk (migration 0010, the 3 markets files, the 3 settlement files, the 2 new-test files, the SUMMARY).
- Both task commits verified in `git log`: `f5ef989` (Task 1), `fd2212c` (Task 2).
- Static gates green: `alembic heads` → single head `0010_phase12_resolution_stakes`; money-lint exit 0 (2 nullable-stake R3 warnings, non-failing); mypy app/markets app/settlement clean.
- Test sweep green: `tests/settlement tests/markets tests/admin/test_kpi.py tests/bets` → 184 passed.
- Migration applied to the project Postgres: `alembic current` == `0010_phase12_resolution_stakes`; 5 columns verified on the live `markets` table.

---
*Phase: 12-admin-market-operations-ui-and-player-resolution-display*
*Completed: 2026-06-03*
