---
phase: 14
slug: curated-per-category-gamma-sync
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-05
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `14-RESEARCH.md` › Validation Architecture (HIGH confidence; live-verified).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio + testcontainers (Postgres 16-alpine) + fakeredis |
| **Config file** | `backend/pyproject.toml` (pytest config) + `backend/tests/conftest.py` (fixtures) |
| **Quick run command** (unit, no Docker) | `cd backend && uv run pytest tests/polymarket/ -m unit -x` |
| **Per-module integration** (the reliable local gate) | `cd backend && uv run pytest tests/polymarket/test_adapter.py -x` |
| **Full suite command** (TRUST LINUX CI — do NOT gate locally) | `cd backend && uv run pytest tests/ -x` |
| **Estimated runtime** | ~5s unit · ~30–60s per integration module |

---

## ⚠️ Windows-worktree test policy (CRITICAL)

This phase executes on a **Windows git-worktree**. The FULL `uv run pytest tests/` suite **flakes here** (testcontainers connection contention across UNRELATED modules) and `ruff check`/`format` flip-flop (file set flickers 148↔202). **Linux CI runs the full suite + ruff + mypy GREEN.** Therefore:

- **Local acceptance gate = PER-MODULE runs** (`test_schemas.py`, `test_adapter.py`, `test_tasks.py`, `test_client.py` individually).
- **Do NOT run / gate on the full `pytest tests/` suite locally.** Use it only on Linux CI.
- Unit tests (`-m unit`) need NO Docker and are always reliable — prefer them for the fast inner loop.
- Ref: `[[xprediction-backend-fullsuite-testcontainers-flake]]` + STATE.md note.

---

## Sampling Rate

- **After every task commit:** `cd backend && uv run pytest tests/polymarket/ -m unit -x` (fast, no Docker)
- **After every plan wave:** per-module integration — `cd backend && uv run pytest tests/polymarket/test_adapter.py tests/polymarket/test_tasks.py -x`
- **Before phase verification:** **Linux CI `backend` job green** (full `pytest tests/` + ruff + mypy) — NOT the Windows worktree
- **Max feedback latency:** ~5s (unit) / ~60s (per-module integration)

---

## Per-Task Verification Map

> Task IDs are assigned by the planner; this maps each phase Success Criterion + the parser to its automated proof. Every row is a NEW or EDITED test (Wave 0 — none exist yet).

| SC / Area | Requirement | Behavior | Test Type | Automated Command | File Exists |
|-----------|-------------|----------|-----------|-------------------|-------------|
| Parser | CAT-01/03, EVT-07 | `GammaEvent`/`GammaTag`/`GammaEventMarket` parse; event-volume float→Decimal; inherited `_derive_status`/validators; first-by-priority → Politics | unit | `uv run pytest tests/polymarket/test_schemas.py -m unit -x` | ❌ W0 (extend) |
| SC#1 | CAT-01 | `market_groups` + grouped children appear in DB from `/events`; `poll_polymarket_top25`→`poll_polymarket_events` @300s in beat | integration + unit | `uv run pytest tests/polymarket/test_adapter.py::test_sync_events_groups_multi_outcome -x` · `…test_tasks.py::test_beat_schedule_swapped -x` | ❌ W0 |
| SC#2 | CAT-02/03/05 | top-N-per-category vs allow-list; dedup by conditionId/event-id BEFORE floor; `limit`≤500 + short-page stop; unmapped tags logged for drift | unit | `uv run pytest tests/polymarket/test_tasks.py -m unit -x` · `…test_client.py::test_fetch_events_caps_limit -x` | ❌ W0 |
| SC#3 | CAT-04/06 | mirrored markets carry populated `category` (group + children); empty category never written (suppression is a Phase-16 read) | integration | `uv run pytest tests/polymarket/test_adapter.py::test_sync_events_groups_multi_outcome -x` (asserts `category=="Crypto"`) | ❌ W0 |
| SC#4 | CAT-05, EVT-07 | Gamma failure keeps last-good per-category (never blanks); `len==1` stays standalone (no group) | unit + integration | `…test_tasks.py::test_poll_events_keeps_last_good_per_category -x` · `…test_adapter.py::test_sync_events_single_market_no_group -x` | ❌ W0 |

*Status legend: ❌ W0 = test does not exist yet, created in Wave 0 · ✅ green · ⚠️ flaky*

---

## Wave 0 Requirements

Fixtures (live-captured this session — DONE):
- [x] `backend/tests/fixtures/gamma/events_multi_outcome.json` — 1 Crypto event, 3 Bitcoin-ladder children, 7 tags
- [x] `backend/tests/fixtures/gamma/events_single_market.json` — `len==1` Politics/World event, dual-tagged
- [x] `backend/tests/fixtures/gamma/tags_categories.json` — the 7 verified category tag_ids

Test scaffolding to add (Wave 0 of execution):
- [ ] `tests/polymarket/conftest.py` — add `gamma_events_multi` / `gamma_events_single` / `gamma_tags_categories` fixtures (loader already exists)
- [ ] `tests/polymarket/test_schemas.py` — add `GammaEvent`/`GammaTag`/`GammaEventMarket` + first-by-priority tests
- [ ] `tests/polymarket/test_adapter.py` — add `sync_events` grouping / EVT-07 / category / dedup / idempotency tests
- [ ] `tests/polymarket/test_tasks.py` — add `poll_polymarket_events` lock + curation + keep-last-good tests AND **edit `test_beat_schedule_entries`** (the existing `"poll-polymarket-top25" in schedule` assertion INVERTS after the swap)
- [ ] `tests/polymarket/test_client.py` — add `fetch_events` params + limit-cap test

*No framework install needed — pytest infra already present.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| redbeat schedule reload (old `poll-polymarket-top25` stops, `poll-polymarket-events` fires) | CAT-01 | redbeat persists the schedule in Redis; a code-only change doesn't re-sync until beat restarts | After deploy/local: restart the beat service (`docker compose restart` beat); confirm `poll_events` logs appear and no further `poll_complete` (top25) logs. Documented as a deploy note. |
| Live `tag_id` drift re-verify | CAT-03 | tag_ids verified 2026-06-05; execute may run days later | Run the 7-slug `GET /tags/slug/{slug}` re-verify loop (RESEARCH.md) at execute start; confirm ids unchanged before relying on the pinned constant. |

---

## Validation Sign-Off

- [ ] All tasks have an `<automated>` verify or a Wave 0 dependency
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (fixtures done; test scaffolds pending)
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s (per-module)
- [ ] `nyquist_compliant: true` set in frontmatter (after planner maps every task)

**Approval:** pending
