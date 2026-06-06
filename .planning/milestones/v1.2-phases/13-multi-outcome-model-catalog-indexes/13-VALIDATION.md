---
phase: 13
slug: multi-outcome-model-catalog-indexes
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-05
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Seeded from `13-RESEARCH.md` › Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio + testcontainers (Postgres 16) |
| **Config file** | `backend/pyproject.toml`; shared fixtures in `backend/tests/conftest.py` |
| **Quick run command** | `cd backend && uv run pytest tests/markets/ -x` |
| **Full suite command** | `cd backend && uv run pytest` |
| **Money lint gate** | `cd backend && uv run python scripts/lint_money_columns.py` (must stay green) |
| **Estimated runtime** | ~60–120 s (testcontainers spins a real PG16 once per session) |

> ⚠️ **Docker dependency:** every command above requires a running Docker daemon (testcontainers
> boots Postgres 16). If Docker is down at execution time, these are the verifications to **defer and
> document** — see Manual-Only / Deferred table below.

---

## Sampling Rate

- **After every task commit:** Run `cd backend && uv run pytest tests/markets/ -x` + `uv run python scripts/lint_money_columns.py`
- **After every plan wave:** Run `cd backend && uv run pytest tests/markets/ tests/bets/ tests/settlement/`
- **Before `/gsd-verify-work`:** Full suite (`cd backend && uv run pytest`) green + money-lint green
- **Max feedback latency:** ~120 seconds

---

## Per-Task Verification Map

> Task IDs are assigned by the planner (`13-XX-YY`); this seeds the SC→test mapping the planner must
> satisfy. Every SC below MUST land in a plan task's `<acceptance_criteria>`.

| SC / Req | Behavior | Test Type | Automated Command | File Exists | Status |
|----------|----------|-----------|-------------------|-------------|--------|
| SC#1 apply+reversible | `0011` upgrades clean; `downgrade()` restores pre-0011 schema | integration (migration) | `cd backend && uv run pytest tests/markets/test_migration_0011.py -x` | ❌ W0 | ⬜ pending |
| SC#1 chain | `0011.down_revision == "0010_phase12_resolution_stakes"`; exactly one head | integration | `cd backend && uv run pytest tests/markets/test_migration_0011.py -k chain -x` | ❌ W0 | ⬜ pending |
| SC#2 zero-change | standalone `group_id IS NULL` market reads/bets/settles unchanged | integration (regression) | `cd backend && uv run pytest tests/markets/test_models.py tests/bets/ tests/settlement/ -x` | ✅ existing + 1 new assertion | ⬜ pending |
| SC#3 pg_trgm+indexes | extension present; all 6 named indexes incl. GIN `gin_trgm_ops` + partial `WHERE` | integration (introspection) | `cd backend && uv run pytest tests/markets/test_migration_0011.py -k index -x` | ❌ W0 | ⬜ pending |
| SC#4 ORM round-trip | parent group loads ≥2 children via `selectinload`; `lazy="raise"` enforced | integration (ORM) | `cd backend && uv run pytest tests/markets/test_models.py -k group -x` | ❌ W0 | ⬜ pending |
| EVT-01 additive | `MKT-08` `trg_binary_outcomes_only` still fires; existing market columns/CHECKs intact | integration (regression) | `cd backend && uv run pytest tests/markets/test_models.py -x` | ✅ existing | ⬜ pending |
| Lint | no money-named column on `market_groups`; lint green | static | `cd backend && uv run python scripts/lint_money_columns.py` | ✅ existing | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/markets/test_migration_0011.py` — NEW. Covers SC#1 (apply + reversibility + chain/down_revision) and SC#3 (pg_trgm extension + all 6 indexes via `pg_indexes.indexdef` introspection, asserting `gin_trgm_ops` opclass and the partial `WHERE source_event_id IS NOT NULL`).
- [ ] `backend/tests/markets/test_models.py` — EXTEND. Add a `MarketGroup` round-trip test (SC#4, `selectinload` parent + ≥2 children), a `Market.group` `lazy="raise"` assertion, and a `group_id IS NULL` standalone-unchanged regression assertion (SC#2).
- [ ] Framework install: **none** — testcontainers + pytest-asyncio already wired in `tests/conftest.py`.

*Existing infrastructure covers SC#2 / EVT-01 regression almost entirely; the only NEW test file is the `0011` migration introspection test. Prefer leaning on existing `tests/bets/` + `tests/settlement/` suites over duplicating end-to-end bet/settle coverage — a pure additive table does not alter those paths, so re-running them green IS the SC#2 proof.*

---

## Manual-Only / Deferred Verifications

| Behavior | Requirement | Why Manual/Deferred | Test Instructions |
|----------|-------------|---------------------|-------------------|
| Any test requiring the live PG16 testcontainer | SC#1–4, EVT-01 | Requires a running Docker daemon; if Docker is down at execute time, these cannot run | Once Docker is up: `cd backend && uv run pytest tests/markets/ -x` then full `uv run pytest`. Mark this row ✅ when green. |

*If Docker is available at execution, there are NO manual-only behaviors — all phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All SCs map to an `<automated>` verify or Wave 0 dependency
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (`test_migration_0011.py`)
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] Docker-dependent rows resolved OR explicitly deferred with re-run instructions
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
