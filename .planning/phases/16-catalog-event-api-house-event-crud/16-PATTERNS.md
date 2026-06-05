# Phase 16: Catalog & Event API + House Event CRUD - Pattern Map

**Mapped:** 2026-06-05
**Files analyzed:** 13 new/modified
**Analogs found:** 13 / 13 (every file has at least a role-match; the two-step-confirm preview is the only piece with NO backend precedent — flagged below)

> All analog file:line references in `16-CONTEXT.md` / `16-RESEARCH.md` were re-verified against the live phase-branch source. Verified-corrected note: the settlement admin router prefix is the **bare `/admin/markets`** (`settlement/router.py:46`) — the "settlement anomaly". The *other* admin surface (`markets/router.py`) uses `/api/v1/admin/markets`. The planner must pick `/admin/events` consistently (spec text says `/admin/events`; mirrors settlement).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/catalog/router.py` (NEW) | router (public) | request-response / CRUD-read | `app/markets/router.py` `public_market_router` (:143-224) + admin paginated list (:52-77) | role+flow exact |
| `app/catalog/service.py` (NEW) | service | CRUD-read / transform | `app/markets/service.py` `list_home_markets` (:243-272) + `list_markets` (:274-302) | role+flow exact |
| `app/catalog/schemas.py` (NEW) | schema | DTO (read) | `app/markets/schemas.py` `MarketListItem` (:156-191) + `OutcomeRead` (:102-113) | role+flow exact |
| `app/settlement/event_router.py` (NEW) | router (admin) | request-response (mutating) | `app/settlement/router.py` resolve/reverse (:59-125) | role+flow exact |
| event request/response schemas (in `app/settlement/schemas.py` OR `app/catalog/schemas.py`) | schema | DTO (request+response) | `app/settlement/schemas.py` `ResolveMarketRequest`/`DecimalStr` (:16-28) + `markets/schemas.py` `MarketCreate` (:67-81) | role+flow exact |
| house-event create path (`EventService.create_house_event` OR `MarketService.create_event`) | service (transactional write) | CRUD-create (batch: 1 group + N children) | `markets/service.py` `create_market` YES/NO body (:38-111) + `integrations/polymarket/adapter.py` `_upsert_market_group` (:319-386) | role+flow exact (composed) |
| event edit-lock + PATCH (in `event_router.py`/service) | service+router | CRUD-update (guarded) | `markets/service.py` `update_market` `CRITERIA_LOCKED` 423 (:128-143) + `bets/models.py` `bets_market_idx` (:76) | role-match (predicate differs: EXISTS not bet_count) |
| resolve/void/reverse endpoints (in `event_router.py`) | router (admin) | request-response → service | `app/settlement/router.py` `resolve_market`/`reverse_settlement` session choreography (:59-125) | role+flow exact |
| two-step confirm preview branch | router (non-mutating read) | request-response (read-only projection) | **NO backend precedent** — `settlement/router.py:5-10` docstring states the two-step flow is a client concern. Composes `EventService._load_group_with_children` (:129) + `derive_event_status` (:98) read-only | NO analog (designed here) |
| `app/main.py` (MODIFIED) | config (router registration) | wiring | `app/main.py` deferred-import + `include_router` block (:180-203) | exact |
| `tests/catalog/test_catalog_router.py` + `test_categories.py` + `test_event_detail.py` (NEW) | test (integration) | request-response assertions | `tests/markets/test_public_router.py` (whole file; back-compat assert :86) | role+flow exact |
| `tests/settlement/test_event_router.py` (NEW) | test (integration) | request-response (admin + auth-gate) | `tests/settlement/test_settlement_router.py` (whole file: `_Admin` override :99-100/:158-159, `ASGITransport` :60-64, `_seed_wallet` :116-134, `_bets_table` :47-51) | role+flow exact |
| `tests/catalog/__init__.py` + `tests/catalog/conftest.py` (NEW) | test (scaffold) | fixtures | reuse `backend/tests/conftest.py` `engine`/`async_session` fixtures + per-module pattern from `test_settlement_router.py:42-64` | role-match |

---

## Pattern Assignments

### `app/catalog/router.py` (NEW — public router, request-response)

**Analog:** `app/markets/router.py` (`public_market_router` :143-224; admin paginated list :52-77)

**Imports + router-decl pattern** (`markets/router.py:1-24,143-146` — note: NO `from __future__ import annotations`; the public router omits it just like settlement does):
```python
from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_async_session

public_market_router = APIRouter(prefix="/api/v1/markets", tags=["markets"])
# → catalog: APIRouter(prefix="/api/v1", tags=["catalog"]); routes /catalog, /events/{slug}, /categories
```

**Public no-auth read endpoint shape** (`markets/router.py:149-155` — flat `list[...]`, NO pagination — exactly the `/catalog` contract):
```python
@public_market_router.get("", response_model=list[MarketListItem])
async def list_markets_public(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[MarketListItem]:
    markets = await MarketService.list_home_markets(session)
    return [MarketListItem.model_validate(m) for m in markets]
# → catalog list endpoint returns list[CatalogItem]; empty filter combo → 200 + [] (BRW-05)
```

**Query-param validation via `Query` + the `Literal` allowlist** (compose `markets/router.py:56-60` `Query(default=...)` with the `Literal` allowlist idiom from `markets/router.py:180` `window: Annotated[Literal["24h","7d","30d"], Query()]`). Use `Literal["open","closing_soon","resolved"]` for `status` and `Literal["volume","closing_soonest","newest"]` for `sort` so FastAPI returns 422 BEFORE the service runs:
```python
# markets/router.py:180 — the allowlist-Query idiom to copy for status/sort
window: Annotated[Literal["24h", "7d", "30d"], Query()] = "7d",
```

**Slug-route 404 shape** (`markets/router.py:158-173` `get_market_public` — mirror for `/events/{slug}`; raise 404 when None OR <2 children):
```python
market = await MarketService.get_market_by_slug(session, slug)
if not market or market.status not in (...):
    raise HTTPException(status_code=404, detail="Market not found")
```

---

### `app/catalog/service.py` (NEW — service, CRUD-read / transform)

**Analog:** `app/markets/service.py` (`list_home_markets` :243-272 — the two-bounded-queries-merged idiom; `list_markets` :274-302 — the conditional query-building)

**Two-bounded-queries pattern (Approach B — copy `list_home_markets` :248-272 structure)** — two `select().options(selectinload(...)).limit(N)`, each executed, results concatenated in Python:
```python
# markets/service.py:249-272 — the EXACT shape to imitate for query A + query B
house_stmt = (
    select(Market)
    .where(Market.source == MarketSourceEnum.HOUSE.value)
    .where(Market.status == MarketStatus.OPEN.value)
    .options(selectinload(Market.outcomes))     # lazy="raise" → MUST eager-load
    .order_by(Market.created_at.desc())
    .limit(50)
)
house_markets = list((await session.execute(house_stmt)).scalars().all())
# ... second query ... return house_markets + pm_markets
```

**Conditional filter-building (copy `list_markets` :284-290)** — chain `.where()` only when the filter is present:
```python
# markets/service.py:284-290 — conditional WHERE chaining for category/status/q
base = select(Market)
if source:   base = base.where(Market.source == source)
if status:   base = base.where(Market.status == status)
if category: base = base.where(Market.category == category)
# → catalog adds: if q: base = base.where(Market.question.ilike(f"%{q}%"))  # bound param, GIN trgm
```

**`scalar_one_or_none()` for the by-slug read (NOT `scalar_one`)** — `markets/service.py:333-334` / `event_service.py:143`:
```python
return result.scalar_one_or_none()   # never scalar_one in the list/detail path (Pitfall 1)
```

**Categories union (CAT-06)** — two `DISTINCT` `select(col)` over the two tables, merged with `set()`; reuse the `Market`/`MarketGroup.category` columns + the eager-`selectinload` discipline. The pattern is plain `select(Market.category).where(...).distinct()` (no existing analog for the union, but the per-table DISTINCT is trivial SQLAlchemy; RESEARCH §Pattern 4 has the exact draft).

**Derived event status — reuse Phase 15 UNCHANGED** (`event_service.py:98-122` `derive_event_status` + `:69-79` `ChildStatus`). Build `ChildStatus(status=child.status, is_yes_winner=...)` exactly like `_derive_status` does (`event_service.py:612-618`):
```python
# event_service.py:613-618 — the exact is_yes_winner construction to copy when assembling event items
yes_id = next((o.id for o in child.outcomes if o.label.upper() == "YES"), None)
is_yes_winner = child.winning_outcome_id is not None and child.winning_outcome_id == yes_id
child_statuses.append(ChildStatus(status=child.status, is_yes_winner=is_yes_winner))
```

**Eager-load chain for event detail (copy `event_service.py:137-143` `_load_group_with_children` verbatim)** — `MarketGroup.markets` and `Market.outcomes` are `lazy="raise"` (`models.py:187,272`):
```python
# event_service.py:139-142 — the eager-load chain to reuse for /events/{slug} + query B
select(MarketGroup)
.where(MarketGroup.id == group_id)   # catalog detail: .where(MarketGroup.slug == slug)
.options(selectinload(MarketGroup.markets).selectinload(Market.outcomes))
```

---

### `app/catalog/schemas.py` (NEW — read DTOs)

**Analog:** `app/markets/schemas.py` (`MarketListItem` :156-191; `OutcomeRead` :102-113)

**`OutcomeRead` — the read DTO + money-as-string serializer to mirror** (`markets/schemas.py:102-113`):
```python
class OutcomeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    label: str
    initial_odds: Decimal
    current_odds: Decimal
    @field_serializer("initial_odds", "current_odds")
    @classmethod
    def serialize_decimal(cls, v: Decimal) -> str:
        return str(v)
```

**`MarketListItem` — the catalog-item read DTO to mirror** (`markets/schemas.py:156-178`; `ConfigDict(from_attributes=True)`; `volume`/`volume_24hr` as JSON strings via `@field_serializer`):
```python
class MarketListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    question: str
    slug: str
    category: str | None
    source: str
    status: str
    deadline: datetime
    bet_count: int
    created_at: datetime
    volume: Decimal = Decimal("0")
    volume_24hr: Decimal = Decimal("0")
    outcomes: list[OutcomeRead]
    @field_serializer("volume", "volume_24hr")
    @classmethod
    def serialize_decimal(cls, v: Decimal) -> str:
        return str(v)
```
> `CatalogItem` adds `type: Literal["market","event"]` discriminator + computes `volume` in Python for events (`sum(child.volume)` — Pitfall 6; `MarketGroup` has NO volume column, `models.py:200-275`). RESEARCH §"Discriminated catalog item schema" (lines 579-610) has the exact recommended shape.

---

### `app/settlement/event_router.py` (NEW — admin router, mutating + preview)

**Analog:** `app/settlement/router.py` (`resolve_market` :59-96; `reverse_settlement` :99-125)

**Module docstring MUST note the `from __future__` omission** (`settlement/router.py:16-18` — load-bearing for FastAPI `Annotated[..., Depends()]` under Python 3.13):
```python
# ``from __future__ import annotations`` intentionally ABSENT — FastAPI 3.13 Annotated-Depends
# gotcha (see app/wallet/admin_router.py). ``User`` / ``AsyncSession`` are runtime imports.
```

**Router decl + admin gate** (`settlement/router.py:27,46`):
```python
from app.auth.deps import current_active_admin
from app.auth.models import User
settlement_admin_router = APIRouter(prefix="/admin/markets", tags=["admin-settlement"])
# → event: APIRouter(prefix="/admin/events", tags=["admin-events"])  (mirror the bare /admin prefix)
```

**THE session-choreography pattern to copy verbatim** (`settlement/router.py:59-96` — capture `admin_id` BEFORE rollback, rollback to clear the autobegun read-tx, call the service which owns its own uow, map `NoResultFound`→404):
```python
@settlement_admin_router.post("/{market_id}/resolve", response_model=ResolveMarketResponse)
async def resolve_market(
    market_id: UUID,
    body: ResolveMarketRequest,
    admin: Annotated[User, Depends(current_active_admin)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    resolver: Annotated[MarketResolvePort, Depends(get_market_resolver)],
) -> ResolveMarketResponse:
    # Capture admin id as a plain value BEFORE the service's begin()/commit churns the
    # session (would expire the dependency-loaded admin -> MissingGreenlet). Then clear
    # the autobegun read tx so resolve_market can open its own unit of work.
    admin_id = admin.id
    await session.rollback()
    try:
        plan = await SettlementService.resolve_market(
            session, market_id=market_id, winning_outcome_id=body.winning_outcome_id,
            market_resolver=resolver, justification=body.justification, actor_user_id=admin_id,
        )
    except NoResultFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="...") from exc
    return ResolveMarketResponse(market_id=market_id, ...)
```
> **CRITICAL — event endpoints call `EventService`, which owns per-child FRESH sessions**, never iterate children on the request session (`event_service.py:464-501` `_settle_children` — the 23505 dangling-tx landmine, `event_service.py:23-31` docstring). The endpoint does `admin_id = admin.id; await session.rollback()` then `await EventService.resolve_event(group_id=..., winning_outcome_id=..., justification=..., actor_user_id=admin_id)`.

**`EventService` signatures the endpoint calls** (`event_service.py:210-218,320-327,382-389`):
```python
EventService.resolve_event(*, group_id, winning_outcome_id, justification, actor_user_id=None) -> EventSettleResult   # :210
EventService.void_event(*, group_id, justification, actor_user_id=None) -> EventSettleResult                          # :320
EventService.reverse_event(*, group_id, justification, actor_user_id=None) -> EventSettleResult                       # :382
# EventSettleResult{group_id, child_count, children_settled, children_failed: tuple[UUID,...], status}  (:82-95)
```

---

### Event request/response schemas

**Analog:** `app/settlement/schemas.py` (`DecimalStr` :16-19; `ResolveMarketRequest` :22-28; `ReverseSettlementRequest` :61-66) + `app/markets/schemas.py` (`MarketCreate` :67-81)

**Request body — `extra="forbid"` + mandatory `Field(min_length=1)` justification** (`settlement/schemas.py:22-28`):
```python
class ResolveMarketRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    winning_outcome_id: UUID
    justification: str = Field(min_length=1, description="Mandatory resolution justification.")
# → ResolveEventRequest adds: confirm: bool = False   (stateless two-step; default = preview)
# → VoidEventRequest / ReverseEventRequest drop winning_outcome_id, keep justification + confirm
```

**`DecimalStr` money-on-the-wire alias** (`settlement/schemas.py:16-19` — for any Decimal in a response):
```python
DecimalStr = Annotated[Decimal, PlainSerializer(lambda v: str(v), return_type=str, when_used="json")]
```

**Create body — `Field(gt=0, lt=1)` odds + nested list with `min_length=2`** (compose `MarketCreate.initial_odds_yes` `markets/schemas.py:71` + the `extra="forbid"` rule). RESEARCH lines 618-630 give the exact `OutcomeInput` / `CreateEventRequest`:
```python
# markets/schemas.py:71 — the odds bound to copy per-outcome
initial_odds_yes: Decimal = Field(default=Decimal("0.5"), gt=0, lt=1)
# → OutcomeInput.initial_odds: Decimal = Field(gt=0, lt=1)
# → CreateEventRequest.outcomes: list[OutcomeInput] = Field(min_length=2)   # ≥2 (EVT-07) → 422
```

---

### House-event create path (`EventService.create_house_event` recommended)

**Analog:** `markets/service.py` `create_market` YES/NO body (:38-111) + `integrations/polymarket/adapter.py` `_upsert_market_group` (:319-386). **Do NOT call `create_market` unchanged** — it has no `group_id`/`group_item_title` param (verified: no `group_id` reference in `markets/service.py`).

**Slug-collision SAVEPOINT-retry idiom** (`markets/service.py:44-69` — wrap the group insert; `generate_slug` already appends a 6-hex suffix so collisions are rare but retry for safety):
```python
# markets/service.py:44-69 — the begin_nested() retry loop to mirror for the group insert
for _attempt in range(3):
    slug = generate_slug(body.question)
    market = Market(question=..., slug=slug, source=MarketSourceEnum.HOUSE.value, status=MarketStatus.OPEN.value, ...)
    session.add(market)
    try:
        nested = await session.begin_nested()
        await session.flush()
        break
    except IntegrityError:
        await nested.rollback()
        session.expunge(market)
else:
    raise HTTPException(status_code=409, detail="Slug collision — try again")
```

**The YES/NO outcome seeding to replicate per child** (`markets/service.py:71-85` — exactly YES + NO, never a 3rd; the binary trigger fires on the 2nd insert):
```python
# markets/service.py:71-84 — the per-child YES/NO body (add group_id + group_item_title to the Market)
odds_no = Decimal("1") - body.initial_odds_yes
yes_outcome = Outcome(market_id=market.id, label="YES", initial_odds=body.initial_odds_yes, current_odds=body.initial_odds_yes)
no_outcome  = Outcome(market_id=market.id, label="NO",  initial_odds=odds_no,                current_odds=odds_no)
session.add_all([yes_outcome, no_outcome])
await session.flush()
```

**Group-create idiom** (`integrations/polymarket/adapter.py:341-378` — the `MarketGroup` value set + SAVEPOINT retry; the house path uses the **request session** + a normal `MarketGroup(...)` insert instead of the Gamma `pg_insert`/upsert):
```python
# adapter.py:342-348 — the MarketGroup columns to set (source=HOUSE for the house path)
values = {"source": MarketSourceEnum.POLYMARKET.value, "source_event_id": ev.id,
          "title": ev.title, "slug": slug_value, "category": category}
# → house: MarketGroup(title=body.title, source=MarketSourceEnum.HOUSE.value,
#          category=body.category, slug=body.slug or generate_slug(body.title))
```

**Hard constraints (verified against source):**
- **`Market.resolution_criteria` is NOT NULL** (`models.py:75` `Mapped[str] = mapped_column(Text, nullable=False)`) — the body must supply or the service must synthesize one per child.
- **Binary-only trigger** `trg_binary_outcomes_only` (migration 0003) blocks a 3rd outcome per `market_id` — each child gets exactly YES + NO. Multi-outcome-ness lives at `market_groups`, not in one market.
- **`generate_slug`** (`models.py:33-36`) wraps `python-slugify` + 6-hex suffix — reuse it, don't hand-roll.
- **`MarketGroup.markets` cascade**: NO `delete-orphan` (`models.py:269-275`); FK is `ON DELETE SET NULL` (`models.py:178`). Pre-bet outcome removal can hard-delete the child + its 2 outcomes (no bets ⇒ no financial rows).

**Audit on create** — mirror `markets/service.py:99-108` `AuditService.record(session, actor=f"user:{admin.id}", event_type="market.created", payload={...})` → `event_type="event.created"`.

---

### Event edit-lock + PATCH (`event_router.py` / service)

**Analog:** `markets/service.py` `update_market` `CRITERIA_LOCKED` 423 (:128-143) + `bets/models.py` `bets_market_idx` (:76)

**The 423-locked pattern to mirror** (`markets/service.py:128-143` returns 423 when a market is not editable) — but the predicate is **`EXISTS(bets)`, NOT the dead `bet_count` column**:
```python
# Lock predicate (RESEARCH §Pattern 6) — bets.market_id is indexed (bets/models.py:50,76)
from sqlalchemy import exists, select
child_ids = select(Market.id).where(Market.group_id == group_id)
has_bets = (await session.execute(select(exists().where(Bet.market_id.in_(child_ids))))).scalar()
if has_bets:
    raise HTTPException(
        status_code=423,
        detail={"code": "EVENT_LOCKED",
                "reason": "Event outcomes/metadata cannot be changed after a bet has been placed"},
    )
```
> **Why EXISTS not `bet_count`:** `markets.bet_count` (`models.py:111-116`) is **dead** — read only at `markets/service.py:136`, never incremented anywhere. The real signal is `EXISTS(SELECT 1 FROM bets WHERE market_id IN (children))`. `bets_market_idx` (`bets/models.py:76`) makes it cheap. Return `status.HTTP_423_LOCKED`, mirroring the market `CRITERIA_LOCKED` 423.

---

### Two-step confirm preview branch (NO backend precedent — designed here)

**Analog:** NONE. `settlement/router.py:5-10` docstring explicitly states: *"The two-step 'propose + confirm' flow is a client concern; this endpoint receives the CONFIRMED resolution."* Phase 16 designs a **stateless** server-side preview.

**Design (composes read-only Phase-15 helpers):**
- `confirm: bool = False` in the request body. `confirm:false`/absent → **200 non-mutating preview**; `confirm:true` → execute via `EventService`.
- **Preview** loads read-only via `_load_group_with_children` (`event_service.py:129-143`) + `derive_event_status` (`event_service.py:98`), validates `winning_outcome_id` belongs to a child's YES leg (mirror the service guard `event_service.py:249-282`), returns impact counts. NO mutation, NO token store, NO server state.
- **Execute** branch runs the session choreography above and calls the service.
- `justification: Field(min_length=1)` is required on BOTH branches (a preview validates the reason early).

**Recommended preview fields** (RESEARCH lines 466-470): resolve `{preview:true, child_count, winners:1, losers:child_count-1, projected_status:"resolved"}`; void `{..., winners:0, losers:child_count, projected_status:"void"}`; reverse `{..., projected_status:"open"}`.

**`ValueError`→HTTP mapping** (`EventService` raises `ValueError`, never `HTTPException`) — the messages to match are at `event_service.py:194-196` (mirrored→409), `:183` (blank justification→422), `:264-282` (bad winning-outcome→422), `:243` (`f"No market group {group_id}."`→404):
```python
# event_service.py:194-196 — "Mirrored (Polymarket) events are admin read-only..."  → 409
# event_service.py:183     — "A non-empty justification is required..."               → 422
# event_service.py:264-282 — "winning_outcome_id ... does not map to exactly one child" / "is not the YES outcome" → 422
# event_service.py:243     — "No market group {group_id}."                            → 404
```
RESEARCH lines 484-494 give the exact `_map_event_value_error` string-match map. Recommendation: also pre-validate the cheap cases in the endpoint so preview + execute return identical 4xx.

---

### `app/main.py` (MODIFIED — router registration)

**Analog:** `app/main.py` deferred-import + `include_router` block (:180-203)

**Register both new routers in the deferred-import block** (`main.py:180-187` imports with `# noqa: E402`, `:189-203` `include_router`):
```python
# main.py:186 — the existing deferred import to extend
from app.markets.router import admin_market_router, public_market_router  # noqa: E402
# ADD:
from app.catalog.router import public_catalog_router          # noqa: E402
from app.settlement.event_router import event_admin_router    # noqa: E402
...
app.include_router(public_catalog_router)   # alongside :197 public_market_router
app.include_router(event_admin_router)      # alongside :201 settlement_admin_router
```
> Deferred imports (`# noqa: E402`, after the app is constructed) avoid circular imports — same as every existing router.

---

### `tests/catalog/*` + `tests/settlement/test_event_router.py` (NEW — integration tests)

**Analogs:** `tests/markets/test_public_router.py` (public reads + back-compat) and `tests/settlement/test_settlement_router.py` (admin + auth-gate).

**httpx `ASGITransport` client fixture** (`test_settlement_router.py:60-64`):
```python
@pytest_asyncio.fixture(loop_scope="session")
async def api() -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

**Markers + testcontainer-required + override-clear fixtures** (`test_settlement_router.py:36-57`):
```python
pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

@pytest.fixture(autouse=True)
def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine:  # the conftest engine fixture
    return engine

@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()
```

**Admin auth override + the real-401 negative** (`test_settlement_router.py:99-100,158-159,169-175`):
```python
class _Admin:
    def __init__(self, user_id: UUID) -> None:
        self.id = user_id

def _admin(user_id: UUID) -> None:
    app.dependency_overrides[current_active_admin] = lambda: _Admin(user_id)

# auth-gate negative — NO override → the real current_active_admin returns 401:
async def test_resolve_requires_admin(api):
    r = await api.post(f"/admin/markets/{uuid4()}/resolve", json={...})
    assert r.status_code == 401
```

**Back-compat assertion to NOT break** (`tests/markets/test_public_router.py:86`): `assert isinstance(body, list)` on `GET /api/v1/markets`. The legacy endpoint stays shape-identical — add new surfaces, don't refactor.

**Bets-table create + wallet/bet seeding for the edit-lock + settle tests** (`test_settlement_router.py:47-51` `_bets_table`, `:116-134` `_seed_wallet`, `:145-155` `_place` via `BetService.place_bet`) — reuse to seed a child with a bet (drives the 423 edit-lock) and to seed open/partial/resolved/void event states.

**Real admin via SQL seed (alternative to override)** — `tests/markets/test_public_router.py:27-40` `_seed_admin` inserts a superuser + logs in for a real Bearer token (use when a true end-to-end admin token is wanted instead of the dependency override).

---

## Shared Patterns

### Admin authentication
**Source:** `app/auth/deps.py` `current_active_admin` (Bearer-only superuser gate); usage `app/settlement/router.py:63`, `app/markets/router.py:43,55`.
**Apply to:** Every `POST/PATCH /admin/events*` endpoint (create, edit, resolve, void, reverse).
```python
from app.auth.deps import current_active_admin
from app.auth.models import User
admin: Annotated[User, Depends(current_active_admin)]
```
Public catalog/event reads are intentionally **unauthenticated** (no `Depends`).

### Money / odds on the wire = JSON strings (never floats)
**Source:** `app/settlement/schemas.py` `DecimalStr` (:16-19); `app/markets/schemas.py` `@field_serializer(..., return str(v))` (:110-113,144-147,175-178).
**Apply to:** Every response carrying `volume` / odds / `initial_odds` / `current_odds` (catalog items, event detail outcomes).
```python
DecimalStr = Annotated[Decimal, PlainSerializer(lambda v: str(v), return_type=str, when_used="json")]
# OR @field_serializer("volume", when_used="json") def _ser(self, v): return str(v)
```

### Session choreography for service calls that churn the session
**Source:** `app/settlement/router.py:71-72,108-109` (`admin_id = admin.id; await session.rollback()`).
**Apply to:** The EXECUTE branch of every resolve/void/reverse event endpoint.
```python
admin_id = admin.id          # capture BEFORE rollback (avoid MissingGreenlet — Pitfall 3)
await session.rollback()     # clear the autobegun read-tx so the service owns its uow
result = await EventService.<op>(group_id=..., justification=..., actor_user_id=admin_id)
```

### Eager-load discipline (`lazy="raise"` relationships)
**Source:** `app/settlement/event_service.py:137-143` `_load_group_with_children`; `app/markets/service.py:253,296` `selectinload(Market.outcomes)`.
**Apply to:** Every read of `MarketGroup.markets` (`models.py:272`) or `Market.outcomes` (`models.py:187`) — both are `lazy="raise"` and raise on bare access (Pitfall 2).
```python
.options(selectinload(MarketGroup.markets).selectinload(Market.outcomes))   # event reads
.options(selectinload(Market.outcomes))                                     # standalone market reads
```

### Request-body validation: `extra="forbid"` + bounded `Field`
**Source:** `app/settlement/schemas.py:25,28` (`ConfigDict(extra="forbid")`, `Field(min_length=1)`); `app/markets/schemas.py:71` (`Field(gt=0, lt=1)`).
**Apply to:** Every event request body (`CreateEventRequest`, `OutcomeInput`, `Resolve/Void/ReverseEventRequest`).

### Audit on every admin mutation
**Source:** `app/markets/service.py:99-108` (`AuditService.record(session, actor=f"user:{admin.id}", event_type=..., payload={...})`); event-level rows already written inside `EventService` (`event_service.py:546-596`).
**Apply to:** The house-event create path (`event.created`). Resolve/void/reverse already audit inside `EventService` — do NOT double-audit.

### Router `from __future__ import annotations` OMISSION
**Source:** `app/settlement/router.py:16-18` (documented); `app/markets/router.py` (omits it).
**Apply to:** `app/catalog/router.py` AND `app/settlement/event_router.py` — the **routers** must omit it (FastAPI `Annotated[..., Depends()]` under Python 3.13, Pitfall 5). The catalog **service** + **schemas** modules MAY keep `from __future__ import annotations` (only the router is affected).

---

## No Analog Found

| File / piece | Role | Data Flow | Reason |
|------|------|-----------|--------|
| Two-step confirm **preview** branch | router (non-mutating projection) | request-response (read-only) | No stateless preview/confirm exists in the backend — `settlement/router.py:5-10` documents that the propose+confirm flow was deliberately a client concern. Design is in RESEARCH §Pattern 7 (lines 421-477); planner uses that, not a code analog. Read-only assembly still reuses `_load_group_with_children` + `derive_event_status`. |
| Catalog **categories union** (`GET /categories`) | service (read) | CRUD-read | No existing endpoint unions DISTINCT across `markets` + `market_groups`. The per-table `select(col).where(...).distinct()` is trivial SQLAlchemy; RESEARCH §Pattern 4 (lines 309-335) has the exact draft. CAT-06 ("never an empty category") is satisfied because a row only appears if a row carries the category. |

> Everything else has a strong same-role + same-data-flow analog on the phase branch; the two items above are the only pieces with no copyable code pattern (both are documented in RESEARCH with concrete drafts).

## Metadata

**Analog search scope:** `backend/app/{catalog (new),markets,settlement,integrations/polymarket,bets,auth,db,core/audit}`, `backend/tests/{markets,settlement}`, `backend/alembic/versions/{0011,0003}`.
**Files scanned (read in full or targeted):** `markets/router.py`, `markets/service.py` (create + list + by-slug), `markets/schemas.py`, `markets/models.py`, `settlement/router.py`, `settlement/schemas.py`, `settlement/event_service.py`, `integrations/polymarket/adapter.py` (group-create), `main.py` (registration block), `bets/models.py` (index), `alembic/versions/0011_phase13_market_groups.py` (indexes + binary-trigger context), `tests/markets/test_public_router.py`, `tests/settlement/test_settlement_router.py`.
**Verification result:** all `16-CONTEXT.md` / `16-RESEARCH.md` file:line references confirmed accurate against live source. One clarification surfaced: the settlement admin prefix is the bare `/admin/markets` (settlement anomaly), not `/api/v1/admin/markets`.
**Pattern extraction date:** 2026-06-05
