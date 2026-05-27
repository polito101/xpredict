---
phase: 04-markets-domain-houseadapter
reviewed: 2026-05-27T22:30:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - backend/app/markets/enums.py
  - backend/app/markets/models.py
  - backend/app/markets/__init__.py
  - backend/app/markets/schemas.py
  - backend/app/markets/service.py
  - backend/app/markets/router.py
  - backend/app/main.py
  - backend/app/integrations/market_source.py
  - backend/app/integrations/__init__.py
  - backend/alembic/versions/0003_phase4_markets.py
  - backend/alembic/env.py
findings:
  critical: 3
  warning: 6
  info: 0
  total: 9
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-05-27T22:30:00Z
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

Phase 4 implements the Markets Domain (Market/Outcome/OddsSnapshot ORM models, MarketSource Protocol + HouseAdapter, admin CRUD API, public read API, Alembic migration 0003, and Pydantic v2 schemas). The overall structure is sound -- clean separation between router/service/models, proper async/await usage, correct audit integration, and a well-authored Alembic migration with a binary-only trigger. However, the review identified three correctness bugs that affect data integrity (allowing updates to resolved/cancelled markets, degenerate 0-probability outcomes, unguarded adapter lookup) and six warnings around missing state guards and input handling gaps.

## Critical Issues

### CR-01: update_market allows modifying RESOLVED and CANCELLED markets

**File:** `backend/app/markets/service.py:80-137`
**Issue:** `update_market` has no status guard. It only checks `bet_count > 0` for `resolution_criteria` locking, but permits any admin to change deadline, category, or odds on a market that is already RESOLVED, CANCELLED, or CLOSED. Modifying odds on a RESOLVED market corrupts the historical record that settlement depends on. Changing the deadline on a CANCELLED market reopens it semantically without changing the status.
**Fix:**
```python
@staticmethod
async def update_market(
    session: AsyncSession,
    market: Market,
    body: MarketUpdate,
    admin_user: User,
    ip: str | None = None,
) -> Market:
    if market.status in (
        MarketStatus.RESOLVED.value,
        MarketStatus.CANCELLED.value,
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MARKET_IMMUTABLE",
                "reason": f"Cannot update market with status {market.status}",
            },
        )
    # ... rest of method
```

### CR-02: initial_odds_yes and odds_yes allow boundary values 0 and 1

**File:** `backend/app/markets/schemas.py:35` and `backend/app/markets/schemas.py:51`
**Issue:** `MarketCreate.initial_odds_yes` uses `ge=0, le=1` and `MarketUpdate.odds_yes` uses the same. This permits creating a market with `initial_odds_yes=0` (YES has 0% probability, NO has 100%) or `initial_odds_yes=1` (YES has 100%, NO has 0%). A 0-probability outcome is degenerate -- it breaks any fair betting math (infinite implied odds), and a 100%-certain outcome is not a prediction market. Both endpoints accept these values and they propagate to the `Numeric(8,6)` column without error.
**Fix:**
```python
# schemas.py - MarketCreate
initial_odds_yes: Decimal = Field(default=Decimal("0.5"), gt=0, lt=1)

# schemas.py - MarketUpdate
odds_yes: Decimal | None = Field(default=None, gt=0, lt=1)
```
Use `gt`/`lt` (exclusive) instead of `ge`/`le` (inclusive) to forbid degenerate boundary values.

### CR-03: get_adapter raises unhandled KeyError on missing source

**File:** `backend/app/integrations/market_source.py:44-45`
**Issue:** `get_adapter(source)` performs a bare dict lookup `REGISTRY[source]`. If a `MarketSourceEnum` value exists that has not been registered (e.g., `POLYMARKET` is defined in the enum but never registered), calling `get_adapter(MarketSourceEnum.POLYMARKET)` raises a raw `KeyError` with no context. Any future caller of this function in a request handler will surface a 500 Internal Server Error instead of an actionable message.
**Fix:**
```python
def get_adapter(source: MarketSourceEnum) -> MarketSource:
    try:
        return REGISTRY[source]
    except KeyError:
        raise ValueError(
            f"No adapter registered for source {source.value!r}. "
            f"Registered: {[s.value for s in REGISTRY]}"
        )
```

## Warnings

### WR-01: bet-check endpoint does not verify deadline has not passed

**File:** `backend/app/markets/router.py:161-174`
**Issue:** The `bet-check` endpoint only checks `market.status != OPEN`. A market can be status=OPEN but have a deadline in the past (if no background job has transitioned it yet). The endpoint would return `{"eligible": True}` for a market whose deadline has already expired, misleading the frontend into showing the bet form for an expired market.
**Fix:**
```python
@public_market_router.get("/{slug}/bet-check")
async def bet_check(
    slug: str,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, bool]:
    market = await MarketService.get_market_by_slug(session, slug)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    if market.status != MarketStatus.OPEN.value:
        raise HTTPException(
            status_code=400,
            detail={"code": "MARKET_NOT_OPEN", "reason": "This market is not accepting bets"},
        )
    if market.deadline <= datetime.now(UTC):
        raise HTTPException(
            status_code=400,
            detail={"code": "MARKET_EXPIRED", "reason": "This market's deadline has passed"},
        )
    return {"eligible": True}
```

### WR-02: MarketUpdate cannot clear category back to null

**File:** `backend/app/markets/schemas.py:52` and `backend/app/markets/service.py:105-107`
**Issue:** `MarketUpdate.category` is typed `str | None = None`, and the service checks `if body.category is not None:`. Since `None` is both the sentinel for "not provided" and the value meaning "clear the field", there is no way for an admin to remove a category once set. Sending `{"category": null}` in JSON deserializes to `None`, which the service interprets as "not provided" and skips the assignment.
**Fix:** Use a sentinel or Pydantic's `model_fields_set` to distinguish "not sent" from "explicitly set to null":
```python
# In service.py update_market:
if "category" in body.model_fields_set:
    market.category = body.category
    changed_fields.append("category")
```
Apply the same pattern to `resolution_criteria` if clearing is desirable.

### WR-03: update_market writes audit even when no fields changed

**File:** `backend/app/markets/service.py:126-137`
**Issue:** If the request body is `{}` (all fields None), `changed_fields` is an empty list, but the audit record is still written with `"changed_fields": []`. This pollutes the audit log with no-op entries, making auditing less useful and potentially inflating the audit_log table.
**Fix:**
```python
if changed_fields:
    await AuditService.record(
        session,
        actor=f"user:{admin_user.id}",
        event_type="market.updated",
        payload={
            "market_id": str(market.id),
            "changed_fields": changed_fields,
        },
        ip=ip,
    )
await session.flush()
```

### WR-04: close_market does not check deadline relationship

**File:** `backend/app/markets/service.py:139-165`
**Issue:** `close_market` only checks `status != OPEN`, but does not verify whether the market deadline has actually passed or whether closing before deadline is an intended admin action. More importantly, there is no guard preventing `update_market` from being called on a CLOSED market. An admin can PATCH odds on a CLOSED market (status check is absent in `update_market`), which also creates OddsSnapshot records for a market that should be frozen.
**Fix:** Add a status guard in `update_market` for CLOSED markets (at minimum for odds changes):
```python
if market.status == MarketStatus.CLOSED.value and body.odds_yes is not None:
    raise HTTPException(
        status_code=409,
        detail={
            "code": "MARKET_CLOSED",
            "reason": "Cannot change odds on a closed market",
        },
    )
```

### WR-05: public market detail endpoint exposes all market statuses

**File:** `backend/app/markets/router.py:150-158`
**Issue:** The public GET `/{slug}` endpoint calls `get_market_by_slug` with no status filter. This means DRAFT markets (which are presumably not meant for public consumption) are accessible to unauthenticated users if they know or guess the slug. The list endpoint correctly filters to OPEN only, but the detail endpoint does not.
**Fix:**
```python
@public_market_router.get("/{slug}", response_model=MarketRead)
async def get_market_public(
    slug: str,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MarketRead:
    market = await MarketService.get_market_by_slug(session, slug)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    if market.status == MarketStatus.DRAFT.value:
        raise HTTPException(status_code=404, detail="Market not found")
    return MarketRead.model_validate(market)
```

### WR-06: Slug collision silently fails on unique constraint

**File:** `backend/app/markets/models.py:27-30` and `backend/app/markets/service.py:25`
**Issue:** `generate_slug` appends a 6-character hex suffix (`uuid4().hex[:6]`), giving 16^6 = ~16.7 million possible suffixes. The slug column has a UNIQUE index. If a collision occurs (same slugified question + same 6-char suffix), the `session.flush()` in `create_market` raises an `IntegrityError` that is not caught, surfacing as a 500 to the client. While unlikely for small datasets, the code has no retry or conflict handling.
**Fix:** Either catch `IntegrityError` on slug collision and retry with a new suffix, or increase the suffix length to make collision negligible:
```python
def generate_slug(question: str) -> str:
    base = _slugify(question, max_length=80)
    suffix = uuid4().hex[:8]  # 16^8 = ~4 billion
    return f"{base}-{suffix}"
```
Or add retry logic in `create_market`.

---

_Reviewed: 2026-05-27T22:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
