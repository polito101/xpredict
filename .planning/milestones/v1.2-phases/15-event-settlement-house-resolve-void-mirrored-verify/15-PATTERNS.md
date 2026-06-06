# Phase 15: Event Settlement (House Resolve/Void + Mirrored Verify) - Pattern Map

**Mapped:** 2026-06-05
**Files analyzed:** 3 new (1 service module containing 2 symbols + 2 test files)
**Analogs found:** 3 / 3 (all exact or strong role-matches — every analog verified against current source this session)

> This is a **backend Python / SQLAlchemy-async orchestration** phase. It COMPOSES the proven
> per-market `SettlementService` over a `MarketGroup`'s children; it does NOT reimplement settlement,
> payout, reversal, audit, or the YES/NO mapping. Every "core pattern" below is an EXISTING idiom to
> copy verbatim, not new logic to invent. The whole risk surface is orchestration discipline:
> fresh-session-per-child (the 23505 landmine), correct YES/NO mapping, derived-status correctness,
> and the mirrored-reject gate.

## File Classification

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `backend/app/settlement/event_service.py` — `EventService` (3 classmethods) | service (orchestration) | event-driven loop over CRUD primitives | `backend/app/settlement/service.py` (`SettlementService`) + `backend/app/integrations/polymarket/tasks.py` (`_run_detect_resolutions` session-per-unit idiom) | exact (role + classmethod + `MarketResolvePort` + audit-in-own-tx) |
| `backend/app/settlement/event_service.py` — `derive_event_status(children)` (module-level pure fn) | utility (pure projection) | transform (read-time, no I/O) | `backend/app/settlement/plan.py` (`build_settlement_plan`) | exact (pure free function, frozen-slots dataclass input, stdlib-only) |
| `backend/tests/settlement/test_event_service.py` | test (integration, testcontainers) | request-response over committed sessions | `backend/tests/settlement/test_resolve_market.py` (committed-session helpers) + `test_force_settle.py` (reject pattern) | exact (committed-session model, `_seed_wallet`/`_place`/`_balance`/`_audit_for_market` helpers, `FakeMarketResolver`/`RaisingMarketResolver`) |
| `backend/tests/settlement/test_derive_event_status.py` | test (pure unit, no DB) | transform | `backend/tests/settlement/test_plan.py` (pure-function unit tests, no Docker) | exact (no fixtures, no testcontainer dependency) |

---

## Pattern Assignments

### `backend/app/settlement/event_service.py` → `EventService` (service, event-driven loop)

**Primary analog:** `backend/app/settlement/service.py` (`SettlementService` — classmethod + port + audit style)
**Secondary analog:** `backend/app/integrations/polymarket/tasks.py` `_run_detect_resolutions` (lines 408-518 — the `_get_session_maker()` per-unit-of-work session idiom + the `HouseMarketResolveAdapter()` + `SettlementService.resolve_market(actor_user_id=None)` call shape)

**Imports pattern** — copy the `from __future__` + `TYPE_CHECKING` async-import discipline from `service.py` lines 30-73 and the in-function lazy import of `_get_session_maker` from `tasks.py` lines 413-415:
```python
from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.audit.service import AuditService
from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import Market, MarketGroup, Outcome
from app.settlement.adapters import HouseMarketResolveAdapter
from app.settlement.service import SettlementService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
```

**Classmethod signature pattern** — mirror `SettlementService.resolve_market` exactly (`service.py` lines 83-93). The event method is a thin loop with the SAME keyword-only style + `actor_user_id: UUID | None = None`:
```python
# Analog: app/settlement/service.py:83-93
class EventService:
    @classmethod
    async def resolve_event(
        cls,
        *,
        group_id: UUID,
        winning_outcome_id: UUID,
        justification: str,
        actor_user_id: UUID | None = None,
    ) -> ...:   # return a small summary dataclass (child_count / settled / failed) — discretion
```
> Adaptation vs the analog: `EventService` methods do NOT take an outer `session` parameter the way
> `SettlementService` does — they own the per-child session lifecycle internally (Pattern 1 below). The
> exact fresh-session factory shape (`_get_session_maker()` vs an injected `async_sessionmaker` param for
> testability) is CONTEXT-discretion (Assumption A4); `_get_session_maker()` is the verified repo default.

**CORE IDIOM — fresh session per child (THE 23505 landmine, Pitfall 1):** This is the single
load-bearing pattern of the phase. Source idiom = `tasks.py` lines 138-145 / 413-415 (`_get_session_maker(); session = session_maker()`) combined with the loop structure. The `EventService` MUST open a FRESH session per child and NEVER chain two `SettlementService` calls in one `with`/`begin()`:
```python
from app.db.session import _get_session_maker   # @lru_cache async_sessionmaker, expire_on_commit=False (db/session.py:42-48)

session_maker = _get_session_maker()
resolver = HouseMarketResolveAdapter()          # the SAME port instance per child (tasks.py:493)
failed: list[UUID] = []

# Child order = winning child FIRST, then losers by market.id (CONTEXT: winners paid before any hiccup).
for child_market_id, child_winning_outcome_id in ordered_children:
    async with session_maker() as child_session:          # FRESH session — never reuse across two settles
        try:
            await SettlementService.resolve_market(        # UNCHANGED — opens its OWN session.begin() (service.py:110)
                child_session,
                market_id=child_market_id,
                winning_outcome_id=child_winning_outcome_id,
                market_resolver=resolver,
                justification=justification,
                actor_user_id=actor_user_id,
            )
        except Exception:                                  # best-effort partial failure (CONTEXT)
            failed.append(child_market_id)
            continue                                       # already-settled siblings stay intact -> partially_resolved
```
> Why fresh-session-per-child and not one outer tx: `SettlementService.resolve_market` and
> `reverse_settlement` EACH wrap `async with session.begin()` internally (`service.py:110` and
> `service.py:277`). A second self-committing call on the same session — especially on the idempotent
> 23505-replay path — hits `InvalidRequestError: A transaction is already begun on this Session`. This
> is the operator-memory landmine that bit the seed harness. The idempotent-replay test is the canary.

**CORE IDIOM — load group + children + outcomes dodging `lazy="raise"` (Pitfall 4):** `MarketGroup.markets`, `Market.outcomes`, and `Market.group` are ALL `lazy="raise"` (`models.py:184-197`, `272-275`). Use `selectinload`, exactly as `tasks.py` does for `Market.outcomes` (lines 350, 423):
```python
# Analog: app/integrations/polymarket/tasks.py:418-424 (selectinload(Market.outcomes))
group = (
    await session.execute(
        select(MarketGroup)
        .where(MarketGroup.id == group_id)
        .options(selectinload(MarketGroup.markets).selectinload(Market.outcomes))
    )
).scalar_one_or_none()
# group.markets and child.outcomes are now safe to access
```

**CORE IDIOM — mirrored-reject gate (EVA-06):** `source` is discriminated on the `MarketGroup` row
via `MarketSourceEnum` (`enums.py:14-16`). The verified analog is the force-settle HOUSE/POLYMARKET
guard at `router.py:152` (`market.source != MarketSourceEnum.POLYMARKET.value`). `EventService`
applies the INVERSE check (reject POLYMARKET groups) in all three methods:
```python
# Analog: app/settlement/router.py:152 (force_settle's source discriminator) + enums.py:14-16
if group.source == MarketSourceEnum.POLYMARKET.value:
    raise ValueError(  # Phase 16 maps this to HTTP 4xx; the service just refuses.
        "Mirrored (Polymarket) events are admin read-only; use force-settle (ADM-06)."
    )
```

**CORE IDIOM — YES/NO outcome mapping (Pattern 2, Pitfall 2):** The winning child settles on its
supplied `winning_outcome_id`; EVERY other child (resolve losers) and EVERY child (void) settles on
its NO outcome. Use the canonical case-insensitive `func.upper(Outcome.label) == "YES"` match — the
verified IN-01 idiom at `app/markets/service.py:374-378` (and `:182`). A case-sensitive `== "YES"`
silently misses mirrored title-case `"Yes"`:
```python
# Analog: app/markets/service.py:374-378 (the canonical IN-01 case-insensitive YES match)
no_outcome_id = (
    await session.execute(
        select(Outcome.id).where(
            Outcome.market_id == child_market_id,
            func.upper(Outcome.label) != "YES",     # the OTHER binary leg = NO
        )
    )
).scalar_one()
```
> Adaptation: in **resolve**, the admin supplies ONE `winning_outcome_id` belonging to ONE child (the
> YES winner); settle that child on the supplied id, every other child on its NO outcome (event-of-binaries:
> exactly one child can be YES — Assumption A1). In **void**, every child settles on its NO outcome (no
> dedicated void code — EVA-04 is all-children-NO, NOT a refund). Open Q2: `resolve_event` should
> defensively confirm the supplied `winning_outcome_id` maps to exactly one child of the group before
> looping, and raise otherwise (cheap guard; the Phase-16 endpoint does the authoritative validation).

**CORE IDIOM — void reuses the resolve loop (EVA-04):** No new code. Call
`SettlementService.resolve_market(child, winning_outcome_id=<that child's NO outcome>)` for EVERY
child. Same loop body as resolve, with the per-child `winning_outcome_id` being the NO leg for all children.

**CORE IDIOM — reverse loops `reverse_settlement` (EVA-05):** Mirror the resolve loop but call
`SettlementService.reverse_settlement` (`service.py:252-261`) per already-settled child on a fresh
session. The `CHECK (balance >= 0)` floor rolls back THAT child only (Pitfall 3 — another reason for
Option A per-child sessions):
```python
# Analog: app/settlement/service.py:252-261 (reverse_settlement contract) + the same fresh-session loop
async with session_maker() as child_session:
    try:
        await SettlementService.reverse_settlement(
            child_session,
            market_id=child_market_id,
            market_resolver=resolver,
            justification=justification,
            actor_user_id=actor_user_id,
        )
    except Exception:        # a winner who spent winnings hits CHECK(balance>=0) -> that child rolls back alone
        failed.append(child_market_id)
        continue
```

**Event-level audit pattern (Pattern 4) — its own small tx AFTER the loop:** The verified analog is
`force_settle` writing its override audit in a SEPARATE `async with session.begin():` AFTER settlement
commits (`router.py:185-199`). Reuse `AuditService.record` (`audit/service.py:27-58`) with the same
`actor=f"user:{actor_user_id}" if ... else "system"` convention `SettlementService` itself uses
(`service.py:237`, `:375`). Write `event.resolved` / `event.voided` / `event.reversed` mirroring the
per-child `settlement.resolved` / `settlement.reversed` rows:
```python
# Analog: app/settlement/router.py:185-199 (action-THEN-audit in a separate begin())
#       + app/settlement/service.py:235-248 (AuditService.record actor + payload shape)
async with session_maker() as audit_session, audit_session.begin():
    await AuditService.record(
        audit_session,
        actor=f"user:{actor_user_id}" if actor_user_id is not None else "system",
        event_type="event.resolved",          # or event.voided / event.reversed
        payload={
            "group_id": str(group_id),
            "winning_outcome_id": str(winning_outcome_id),  # omit/None for void
            "child_count": len(children),
            "children_settled": len(children) - len(failed),
            "children_failed": [str(x) for x in failed],
            "justification": justification,
        },
    )
```
> `AuditService.record` only flushes (caller owns the tx — `audit/service.py:37-48`), so it MUST run
> inside the `audit_session.begin()` block. Payload field names are CONTEXT-discretion; money (if any)
> is always a STRING, never a JSON float (the `service.py:244-246` convention) — though the event row
> carries no money, only counts + ids.

**Validation pattern:** `justification` mandatory non-blank at the service layer — raise on blank/whitespace BEFORE looping (CONTEXT: EVA-03 two-step confirm is a Phase 16/17 UI concern; the service just enforces non-empty). No existing analog raises on blank justification (the routers pass `body.justification` through), so this is a small new guard: `if not justification or not justification.strip(): raise ValueError(...)`.

---

### `backend/app/settlement/event_service.py` → `derive_event_status(children)` (utility, pure projection, EVT-06)

**Analog:** `backend/app/settlement/plan.py` (`build_settlement_plan` — pure free function, frozen-slots dataclass input, no I/O, no ORM)

**Why this analog:** `build_settlement_plan` (`plan.py:61-106`) is the repo's canonical pure-projection
idiom: a module-level free function (NOT a classmethod) operating on a `Sequence` of frozen-slots
dataclasses (`BetToSettle`, `plan.py:30-37`), returning a frozen-slots result, with a docstring noting
"No I/O, no ORM" and "Pure and total — an empty market yields an empty plan." `derive_event_status`
follows this shape exactly so it is trivially unit-testable without a session.

**Pure-dataclass-input pattern** — copy the `@dataclass(frozen=True, slots=True)` idiom from `plan.py:30-58`:
```python
# Analog: app/settlement/plan.py:30-37 (BetToSettle frozen-slots input dataclass)
from __future__ import annotations
from collections.abc import Sequence
from dataclasses import dataclass
from app.markets.enums import MarketStatus    # str enum, values DRAFT/OPEN/CLOSED/RESOLVED/CANCELLED (enums.py:6-11)

@dataclass(frozen=True, slots=True)
class ChildStatus:
    """Minimal per-child facts (decoupled from the ORM so the unit test needs no session)."""
    status: str            # Market.status value
    is_yes_winner: bool    # this child resolved with its YES outcome as the winner
```

**Pure-function core pattern** — mirror `build_settlement_plan`'s total/empty-safe classification (`plan.py:61-106`):
```python
# Analog: app/settlement/plan.py:61-106 (pure classification, empty-safe, total)
def derive_event_status(children: Sequence[ChildStatus]) -> str:
    if not children:
        return "open"
    resolved = [c for c in children if c.status == MarketStatus.RESOLVED.value]
    n_resolved, n_total = len(resolved), len(children)
    if n_resolved == 0:
        return "open"
    if n_resolved < n_total:
        return "partially_resolved"
    # all children resolved -> resolved (exactly one YES winner) vs void (no YES winner).
    return "resolved" if any(c.is_yes_winner for c in resolved) else "void"
```
> `is_yes_winner` mapping when projecting from REAL rows: a child "won YES" when its persisted
> `Market.winning_outcome_id` (`models.py:143-146`) equals that child's YES outcome id
> (`func.upper(label)=="YES"`). The service computes this boolean; the unit test passes it directly.
> Status set is EXACTLY `{open, partially_resolved, resolved, void}` (the roadmap's four). NO stored
> column on `market_groups` — `MarketGroup` (`models.py:200-275`) deliberately has NO `status`/`winning_outcome`
> (EVT-06); do not add one.

---

### `backend/tests/settlement/test_event_service.py` (test, integration, testcontainers)

**Primary analog:** `backend/tests/settlement/test_resolve_market.py` (the committed-session integration idiom)
**Secondary analog:** `backend/tests/settlement/test_force_settle.py:171-196` (the reject-pattern assertions for the mirrored-reject test)

**CRITICAL — committed-vs-rolled-back session model (Pitfall 5):** `SettlementService` (and therefore
`EventService`) commits internally, so the test act CANNOT use the `async_session` fixture
(`conftest.py:187-210` wraps each test in a rolled-back tx). It MUST use real committed
`_get_session_maker()` sessions and assert against COMMITTED state, exactly as
`test_resolve_market.py` does. The session-scoped container + per-test fresh UUIDs provide isolation.

**Test-module header pattern** — copy `test_resolve_market.py:58-76` verbatim:
```python
# Analog: test_resolve_market.py:58-76
pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]

@pytest.fixture(autouse=True)
def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine:
    return engine

@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _bets_table(engine: AsyncEngine):
    async with engine.begin() as conn:
        await conn.run_sync(Bet.__table__.create, checkfirst=True)
    yield
```

**Committed-session helpers to copy** — `test_resolve_market.py` lines 158-302 are the directly
reusable toolkit. Copy `_seed_wallet` (`:158-178`), `_balance` (`:181-187`), `_liability_id`
(`:189-202`), `_bets_for_user` (`:204-208`), `_place` (`:210-221`), `_resolve` (`:223-241`),
`_audit_for_market` (`:287-302`), and the `FakeMarketResolver` / `RaisingMarketResolver` classes
(`:93-135`):
```python
# Analog: test_resolve_market.py:158-178 (the committed _seed_wallet idiom — own _get_session_maker() + s.begin())
async def _seed_wallet(balance: Decimal) -> tuple[UUID, UUID]:
    user_id = uuid4()
    wallet_id = uuid4()
    sm = _get_session_maker()
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO accounts (id, owner_type, owner_id, kind, currency, balance) "
                "VALUES (:id, :ot, :oid, :kind, :cur, :bal)"
            ),
            {"id": wallet_id, "ot": OWNER_USER, "oid": user_id,
             "kind": KIND_USER_WALLET, "cur": PLAY_USD, "bal": balance},
        )
    return user_id, wallet_id
```

**NEW helper required — `_seed_house_event(n_children, ...)`:** There is NO existing house-event seed
(Phase 18 ships the seed harness), so the test file MUST build one — a committed `market_groups` row +
N HOUSE child markets each with YES/NO `Outcome` rows + placed bets. Model it on
`test_resolve_market.py`'s `_seed_real_market` (`:244-277`, which builds a `Market` + its `Outcome`
rows on a committed `s.begin()` session) and extend it to first INSERT a `MarketGroup` and stamp each
child's `group_id`/`group_item_title`:
```python
# Analog: test_resolve_market.py:244-277 (_seed_real_market: committed Market + Outcomes)
#         extended with a MarketGroup parent (models.py:200-275) + child.group_id stamping (models.py:176-182)
async def _seed_house_event(n_children: int, ...) -> tuple[UUID, list[...]]:
    from app.markets.models import Market, MarketGroup, Outcome
    sm = _get_session_maker()
    async with sm() as s, s.begin():
        group = MarketGroup(
            id=uuid4(), title="...", slug=f"evt-{uuid4().hex[:8]}",
            source=MarketSourceEnum.HOUSE.value,
        )
        s.add(group)
        await s.flush()
        # ... N child Markets with group_id=group.id, each + "YES"/"NO" Outcome rows ...
```

**Integrity-check idiom (the spike-004 gate, Open Q1):** After EVERY resolve/void/reverse/partial/replay
path, assert ledger cleanliness. The verified reusable detector is
`app.wallet.reconcile._reconcile_async` (`reconcile.py:61-85`), which accepts an injected session and
returns `{"accounts_checked", "drift_count"}`:
```python
# Analog: app/wallet/reconcile.py:61-85 + RESEARCH Code Examples
import app.wallet.reconcile as reconcile
from app.db.session import _get_session_maker

async def _assert_ledger_clean() -> None:
    sm = _get_session_maker()
    async with sm() as s:
        summary = await reconcile._reconcile_async(s)
    assert summary["drift_count"] == 0   # house_promo excluded by design (reconcile.py:50)
```
> RESEARCH Open Q1 recommendation: do BOTH where cheap — assert per-market liability drains to 0 and
> house deltas match (the fast precise `test_resolve_market.py` style, e.g. `:339-342`) AND call
> `_reconcile_async(fresh_session)` asserting `drift_count == 0` (the literal integrity gate). Use
> before/after DELTAS on the shared `HOUSE_PROMO_ACCOUNT_ID`/`HOUSE_REVENUE_ACCOUNT_ID` singletons,
> absolute values only on per-test fresh accounts (the pattern `test_resolve_market.py:321-342` uses).

**Mirrored-reject test pattern** — analog `test_force_settle.py:171-183` (seed a non-matching-source
market, assert the rejection). For `EventService` the service raises (not HTTP yet — Phase 16), so the
test seeds a `source=POLYMARKET` `MarketGroup` and asserts `EventService.resolve_event` raises:
```python
# Analog: test_force_settle.py:171-183 (reject pattern) adapted to a service-layer raise
with pytest.raises(ValueError):   # mirrored groups are admin read-only (EVA-06)
    await EventService.resolve_event(group_id=mirrored_group_id, ...)
```

**Idempotent-replay test (the canary for Pitfall 1):** Resolve the event, then resolve the SAME group
AGAIN; assert the second pass settles nothing (children no longer PENDING) and no double-credit —
mirroring `test_resolve_market.py:419-445` (`test_resolve_market_is_idempotent`) at the event level.
This test is what catches a same-session 23505 dangling-tx regression.

> Do NOT write a resolve -> reverse -> RE-resolve test expecting success — that is a KNOWN deferred gap
> (Pitfall 6: `reverse_idempotency_key` docstring at `constants.py:66-69` — re-resolution-after-reversal
> reuses `settle:{bet_id}:{leg}` keys and collides on 23505). Scope reverse to "restore + audit" only.

---

### `backend/tests/settlement/test_derive_event_status.py` (test, pure unit, no DB)

**Analog:** `backend/tests/settlement/test_plan.py` (pure-function unit tests for `build_settlement_plan` — no fixtures, no testcontainer, runnable without Docker)

**Why this analog:** `derive_event_status` is pure (like `build_settlement_plan`), so its tests need
NO `engine`/`async_session` fixtures and NO `pytest.mark.integration`. They construct `ChildStatus`
inputs directly and assert the returned string. Mirror `test_plan.py`'s direct-construct-and-assert
style. Quick run: `cd backend && uv run pytest tests/settlement/test_derive_event_status.py -x`
(pure unit, no Docker — RESEARCH Validation Architecture).

**Cases to cover (EVT-06):** empty -> `open`; no child resolved -> `open`; some resolved -> `partially_resolved`; all resolved with one YES winner -> `resolved`; all resolved with NO YES winner -> `void` (the void edge).

---

## Shared Patterns

### Fresh-session-per-unit-of-work factory
**Source:** `backend/app/db/session.py:42-48` (`_get_session_maker()` — `@lru_cache async_sessionmaker`, `expire_on_commit=False`)
**Apply to:** `EventService` (per child + per audit row) AND all committed test helpers.
```python
from app.db.session import _get_session_maker
session_maker = _get_session_maker()
async with session_maker() as session:   # one unit of work; the service owns the begin() inside
    ...
```
Verified in-use across `tasks.py:141-145`, `:413-415`, `reconcile.py:82-84`, and every `test_resolve_market.py` helper. This is THE non-negotiable factory for the phase (Pitfall 1).

### Audit row via `AuditService.record`
**Source:** `backend/app/core/audit/service.py:27-58` (`record(session, *, actor, event_type, payload, ip=None, tenant_id=None)`)
**Apply to:** the event-level `event.resolved`/`event.voided`/`event.reversed` rows.
```python
await AuditService.record(session, actor=..., event_type="event.resolved", payload={...})
```
Caller owns the tx (record only flushes). Actor convention `f"user:{actor_user_id}"` / `"system"` is copied from `service.py:237`/`:375`. The event row is ADDITIONAL to the per-child `settlement.*` rows `SettlementService` already writes (`service.py:235-248`, `:373-383`).

### `MarketResolvePort` injection
**Source:** `backend/app/settlement/market_port.py:23-54` (`@runtime_checkable Protocol`) + `backend/app/settlement/adapters.py:29-58` (`HouseMarketResolveAdapter`)
**Apply to:** pass the SAME `HouseMarketResolveAdapter()` instance per child (exactly as `tasks.py:493` does). The adapter writes on the caller's session and MUST NOT commit — `SettlementService` owns the tx. The event loop adds NO status transition of its own (the spike-002 closed-vs-resolved guard inside the adapter/service stays the only path to a child `MarketStatus`).

### Case-insensitive YES/NO label match (IN-01)
**Source:** `backend/app/markets/service.py:374-378` (and `:182`) — `func.upper(Outcome.label) == "YES"`
**Apply to:** every winning/NO outcome lookup in `EventService` (Pattern 2 / Pitfall 2). House labels are `"YES"`/`"NO"`; mirrored Polymarket labels are title-case `"Yes"`/`"No"` (never normalized). A case-sensitive `== "YES"` silently misses mirrored data.

### Mirrored auto-settle path (EVA-06 — VERIFY, do not rebuild)
**Source:** `backend/app/integrations/polymarket/tasks.py:380-518` (`_run_detect_resolutions`) — calls `SettlementService.resolve_market(actor_user_id=None)` per market (lines 489-496) on the 60s Celery beat with its own `DETECT_LOCK_KEY` Redis lock.
**Apply to:** Phase 15 VERIFIES this path against real Phase-14 `market_groups` data read-only — it does NOT call or modify it, does NOT alter the beat schedule or locks. `EventService` REFUSES mirrored groups (the reject gate above); mirrored children settle individually through this task. The force-settle exception (ADM-06) lives at `router.py:133-208`.

---

## No Analog Found

| File / Concern | Role | Reason | Planner Action |
|----------------|------|--------|----------------|
| (none — all four files have strong analogs) | — | — | — |

Two SMALL idioms have no direct analog and are net-new (but are trivial and bounded):
- **Blank-justification guard** — no existing service raises on whitespace justification (routers pass it through). New 2-line guard in each `EventService` method: `if not justification or not justification.strip(): raise ValueError(...)`. (CONTEXT V5 input-validation rule.)
- **`_seed_house_event` test helper** — no house-event seed exists pre-Phase-18. Build it by extending `test_resolve_market.py:244-277` (`_seed_real_market`) with a parent `MarketGroup` (`models.py:200-275`) + `group_id` stamping (`models.py:176-182`).

---

## Metadata

**Analog search scope:** `backend/app/settlement/`, `backend/app/markets/`, `backend/app/integrations/polymarket/`, `backend/app/core/audit/`, `backend/app/db/`, `backend/app/wallet/`, `backend/tests/settlement/`, `backend/tests/conftest.py`
**Files scanned (read in full or targeted):** 14 — `settlement/service.py`, `settlement/market_port.py`, `settlement/plan.py`, `settlement/adapters.py`, `settlement/constants.py`, `settlement/router.py`, `markets/models.py`, `markets/enums.py`, `markets/service.py` (targeted), `core/audit/service.py`, `db/session.py`, `integrations/polymarket/tasks.py`, `wallet/reconcile.py`, `tests/settlement/test_resolve_market.py`, `tests/settlement/test_force_settle.py` (targeted), `tests/conftest.py`
**Pattern extraction date:** 2026-06-05
**All analogs verified against current source this session** — no assumed line numbers; every excerpt read directly.
