# Phase 7: Polymarket Auto-Resolution & Admin Override - Pattern Map

**Mapped:** 2026-05-28
**Files analyzed:** 9
**Analogs found:** 9 / 9

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/alembic/versions/0007_phase7_grace_period.py` | migration | batch | `backend/alembic/versions/0004_phase6_polymarket_sync.py` | exact |
| `backend/app/core/config.py` | config | — | `backend/app/core/config.py` (self, Phase 6 section) | exact |
| `backend/app/integrations/polymarket/adapter.py` | service | request-response | `backend/app/integrations/polymarket/adapter.py` (self, `sync_top25`) | exact |
| `backend/app/integrations/polymarket/tasks.py` | service | event-driven | `backend/app/integrations/polymarket/tasks.py` (self, `_run_poll_sync`) | exact |
| `backend/app/celery_app.py` | config | event-driven | `backend/app/celery_app.py` (self, beat_schedule.update) | exact |
| `backend/app/markets/models.py` | model | CRUD | `backend/app/markets/models.py` (self, nullable DateTime columns) | exact |
| `backend/app/settlement/router.py` | controller | request-response | `backend/app/settlement/router.py` (self, `resolve_market` endpoint) | exact |
| `backend/tests/polymarket/test_detect_resolution.py` | test | — | `backend/tests/polymarket/test_tasks.py` + `test_schemas.py` | role-match |
| `backend/tests/settlement/test_force_settle.py` | test | — | `backend/tests/settlement/test_settlement_router.py` | exact |

---

## Pattern Assignments

### `backend/alembic/versions/0007_phase7_grace_period.py` (migration, batch)

**Analog:** `backend/alembic/versions/0004_phase6_polymarket_sync.py`

**File header + revision chain** (lines 1–24):
```python
"""Phase 7 grace period: uma_resolved_at column for auto-resolution gating.

Revision ID: 0007_phase7_grace_period
Revises: 0006_merge_phase5_phase6
Create Date: 2026-05-28

Adds a nullable DateTime(timezone=True) column to the markets table that records
the first time the Beat task observed umaResolutionStatus='resolved' for a
Polymarket-mirrored market. All existing rows receive NULL (safe default — no
grace period is currently in progress). STL-01 grace-period state.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0007_phase7_grace_period"
down_revision: str | None = "0006_merge_phase5_phase6"
branch_labels: str | None = None
depends_on: str | None = None
```

**Core upgrade/downgrade pattern** (from analog lines 27–106):
```python
def upgrade() -> None:
    op.add_column(
        "markets",
        sa.Column(
            "uma_resolved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("markets", "uma_resolved_at")
```

**Key invariant:** No `server_default`, no `NOT NULL` — nullable column, all existing rows get NULL automatically. This is identical to how `closed_at` and `resolved_at` are added in the markets table (both nullable DateTime(timezone=True) with no default).

---

### `backend/app/core/config.py` (config, Phase 6 append pattern)

**Analog:** `backend/app/core/config.py` lines 84–89 (Phase 6 section)

**Phase 6 section to copy pattern from** (lines 84–89):
```python
    # -------------------------------------------------------------------------
    # Phase 6 — Polymarket Sync (MKT-05, MKT-06)
    # -------------------------------------------------------------------------
    GAMMA_API_BASE_URL: str = "https://gamma-api.polymarket.com"
    POLYMARKET_POLL_INTERVAL_SECONDS: int = 30
    POLYMARKET_SNAPSHOT_INTERVAL_SECONDS: int = 300
    POLYMARKET_LOCK_TTL_SECONDS: int = 25
```

**New Phase 7 section to append** (same pattern):
```python
    # -------------------------------------------------------------------------
    # Phase 7 — Polymarket Auto-Resolution (STL-01)
    # -------------------------------------------------------------------------
    POLYMARKET_GRACE_PERIOD_MINUTES: int = 30
```

**Placement:** Append directly after the Phase 6 block, before the `@property` methods.

---

### `backend/app/integrations/polymarket/adapter.py` (service, request-response)

**Analog:** `backend/app/integrations/polymarket/adapter.py` — `detect_resolution` stub (line 67–71) and `sync_top25` outcome loop (lines 73–194)

**Current stub to REPLACE** (lines 67–71):
```python
    async def detect_resolution(
        self, session: AsyncSession, market_id: UUID,
    ) -> ResolutionResult | None:
        """Phase 6 stub — returns None. Phase 7 implements real detection."""
        return None
```

**Outcome label loop to INVERT for `_map_winning_outcome_id`** (lines 151–177):
```python
                if parsed.outcomes_raw and parsed.outcome_prices_raw:
                    for idx, label in enumerate(parsed.outcomes_raw[:2]):
                        price = (
                            Decimal(parsed.outcome_prices_raw[idx])
                            if idx < len(parsed.outcome_prices_raw)
                            else Decimal("0.5")
                        )
                        existing = await session.execute(
                            select(Outcome).where(
                                Outcome.market_id == market.id,
                                Outcome.label == label[:50],
                            ),
                        )
```

**Import additions needed** (based on analog lines 1–32):
```python
from datetime import UTC, datetime, timedelta  # already imported
# Add:
from app.integrations.polymarket.client import GammaClient
from app.markets.enums import MarketStatus  # already available via schemas
from app.settlement.adapters import HouseMarketResolveAdapter
from app.settlement.service import SettlementService
```

**Warning:** `adapter.py` has `from __future__ import annotations` at line 1 — this is ALLOWED here (unlike router files) because it is not a FastAPI handler file.

---

### `backend/app/integrations/polymarket/tasks.py` (service, event-driven)

**Analog:** `backend/app/integrations/polymarket/tasks.py` — `_run_poll_sync` (lines 53–104) and the `@celery_app.task` decorator pattern (lines 156–165)

**Lock pattern to copy** (lines 33–45):
```python
LOCK_KEY = "xpredict:poll:polymarket:lock"

async def acquire_poll_lock(redis: AioRedis) -> bool:
    settings = get_settings()
    ttl = settings.POLYMARKET_LOCK_TTL_SECONDS
    acquired = await redis.set(LOCK_KEY, "1", nx=True, ex=ttl)
    return bool(acquired)

async def release_poll_lock(redis: AioRedis) -> None:
    await redis.delete(LOCK_KEY)
```

**New task key for Phase 7** — use `"xpredict:detect:polymarket:lock"` (distinct from poll lock per RESEARCH anti-pattern note).

**Async inner function + session factory pattern** (lines 53–104):
```python
async def _run_poll_sync(
    *,
    redis_override: AioRedis | None = None,
    session_override: AsyncSession | None = None,
) -> None:
    """Async logic for poll_polymarket_top25 — testable with injected deps."""
    settings = get_settings()

    redis: AioRedis
    if redis_override is not None:
        redis = redis_override
    else:
        redis = AioRedis.from_url(str(settings.REDIS_URL))

    if not await acquire_poll_lock(redis):
        log.info("poll_skipped", reason="lock_held")
        return

    client = GammaClient()
    session: AsyncSession | None = None
    try:
        # ... main logic ...
        if session_override is not None:
            session = session_override
        else:
            from app.db.session import _get_session_maker
            session_maker = _get_session_maker()
            session = session_maker()
        try:
            # ... adapter calls ...
            await session.commit()
        finally:
            if session_override is None:
                await session.close()
    except Exception as exc:
        log.error("poll_failed", error=str(exc))
        sentry_sdk.capture_exception(exc)
        if session is not None:
            with contextlib.suppress(Exception):
                await session.rollback()
    finally:
        await release_poll_lock(redis)
        await client.close()
        if redis_override is None:
            await redis.aclose()
```

**Celery task wrapper pattern** (lines 156–159):
```python
@celery_app.task(name="app.integrations.polymarket.tasks.poll_polymarket_top25")
def poll_polymarket_top25() -> None:
    """Celery task wrapping _run_poll_sync in asyncio.run."""
    asyncio.run(_run_poll_sync())
```

**DB candidate query to follow** (from `_run_snapshot_odds`, lines 122–128):
```python
    stmt = (
        select(Market)
        .where(Market.status == MarketStatus.OPEN.value)
        .options(selectinload(Market.outcomes))
    )
    result = await session.execute(stmt)
    markets = list(result.scalars().all())
```

Phase 7 adds `.where(Market.source == MarketSourceEnum.POLYMARKET.value)` and `.where(Market.deadline < now)` to this pattern.

---

### `backend/app/celery_app.py` (config, event-driven)

**Analog:** `backend/app/celery_app.py` lines 71–78 (`.update()` call pattern)

**Existing `.update()` pattern** (lines 71–78):
```python
celery_app.conf.beat_schedule.update(
    {
        "reconcile-wallets-nightly": {
            "task": "app.wallet.reconcile.reconcile_wallets",
            "schedule": crontab(hour=3, minute=0),
        },
    }
)
```

**Phase 7 addition** — add to the existing inline `beat_schedule` dict OR via a second `.update()` after line 78:
```python
celery_app.conf.beat_schedule.update(
    {
        "detect-polymarket-resolutions": {
            "task": "app.integrations.polymarket.tasks.detect_polymarket_resolutions",
            "schedule": 60.0,  # STL-01: every 60 seconds
        },
    }
)
```

**Comment to update** (line 59): `# Phases 7-9 append tasks here` — this signals the exact insertion point in the inline dict. Either add to the inline dict directly or use a second `.update()` call (both patterns already exist in the file).

---

### `backend/app/markets/models.py` (model, CRUD)

**Analog:** `backend/app/markets/models.py` — `closed_at` and `resolved_at` nullable DateTime columns (lines 92–97)

**Existing nullable DateTime pattern** (lines 92–97):
```python
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
```

**New column to add** — insert after `resolved_at` (line 97):
```python
    uma_resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
```

No `from __future__ import annotations` is present (line 1 of models.py only imports `from __future__ import annotations` — CONFIRMED: line 1 IS `from __future__ import annotations`). This is fine for SQLAlchemy ORM models.

---

### `backend/app/settlement/router.py` (controller, request-response)

**Analog:** `backend/app/settlement/router.py` — `resolve_market` endpoint (lines 53–90)

**File header guard** (from docstring line 17):
```python
# ``from __future__ import annotations`` intentionally ABSENT — FastAPI 3.13 Annotated-Depends
# gotcha (see app/wallet/admin_router.py). ``User`` / ``AsyncSession`` are runtime imports.
```
CRITICAL: Do NOT add `from __future__ import annotations` to this file.

**Existing endpoint pattern to copy** (lines 53–90):
```python
@settlement_admin_router.post("/{market_id}/resolve", response_model=ResolveMarketResponse)
async def resolve_market(
    market_id: UUID,
    body: ResolveMarketRequest,
    admin: Annotated[User, Depends(current_active_admin)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    resolver: Annotated[MarketResolvePort, Depends(get_market_resolver)],
) -> ResolveMarketResponse:
    admin_id = admin.id
    await session.rollback()

    try:
        plan = await SettlementService.resolve_market(
            session,
            market_id=market_id,
            winning_outcome_id=body.winning_outcome_id,
            market_resolver=resolver,
            justification=body.justification,
            actor_user_id=admin_id,
        )
    except NoResultFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Market or its ledger account not found.",
        ) from exc

    return ResolveMarketResponse(...)
```

**New imports needed** (add to existing import block):
```python
from app.integrations.polymarket.client import GammaClient
from app.core.audit.service import AuditService
from app.markets.models import Market
from app.markets.enums import MarketSourceEnum
```

**`AuditService.record` signature** (from `app/core/audit/service.py` lines 27–36):
```python
    @staticmethod
    async def record(
        session: AsyncSession,
        *,
        actor: str,
        event_type: str,
        payload: dict[str, Any],
        ip: str | None = None,
        tenant_id: UUID | None = None,
    ) -> AuditLog:
```

**Transaction boundary rule** (from RESEARCH.md Pattern 4 + service.py docstring): `SettlementService.resolve_market` uses `async with session.begin()` internally and commits. After it returns, the session is in a clean state. The force-settle handler must call `await session.rollback()` at the top (same as existing endpoints), then after `resolve_market` commits, open a NEW `async with session.begin()` for the `AuditService.record` call. Do NOT try to share the transaction.

**New schemas to add to `settlement/schemas.py`:**
```python
class ForceSettleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    winning_outcome_id: UUID
    justification: str = Field(min_length=1, description="Mandatory force-settle justification.")


class ForceSettleResponse(BaseModel):
    market_id: UUID
    winning_outcome_id: UUID
    bets_settled: int
    total_payout: DecimalStr
    total_loser_stake: DecimalStr
    uma_status_at_override: str | None
```

---

### `backend/tests/polymarket/test_detect_resolution.py` (test)

**Analogs:** `backend/tests/polymarket/test_tasks.py` (unit mock pattern) + `backend/tests/polymarket/test_schemas.py` (VCR fixture + GammaMarket.model_validate pattern) + `backend/tests/polymarket/conftest.py` (fixture loading)

**Unit test structure** (from `test_tasks.py` lines 29–108):
```python
pytestmark_unit = [pytest.mark.unit]

@pytest.mark.unit
async def test_acquire_poll_lock_calls_setnx() -> None:
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    result = await acquire_poll_lock(redis)
    assert result is True
    redis.set.assert_called_once()
```

**VCR fixture access** (from `conftest.py` lines 19–36):
```python
@pytest.fixture
def gamma_resolved() -> dict:
    return load_gamma_fixture("resolved_market")

@pytest.fixture
def gamma_closed_not_resolved() -> dict:
    return load_gamma_fixture("closed_not_resolved")
```

**SC#3 pattern from `test_schemas.py`** (lines 30–38):
```python
def test_closed_not_resolved(self, gamma_closed_not_resolved: dict) -> None:
    """CRITICAL: closed=true + umaResolutionStatus=proposed -> CLOSED (not RESOLVED)."""
    market = GammaMarket.model_validate(gamma_closed_not_resolved)
    assert market.internal_status == MarketStatus.CLOSED
    assert market.internal_status != MarketStatus.RESOLVED
```

**Mock patch style for GammaClient** (from `test_tasks.py` lines 62–67):
```python
    with patch(
        "app.integrations.polymarket.tasks.GammaClient",
    ) as mock_client_cls:
        await _run_poll_sync(redis_override=redis)
        mock_client_cls.assert_not_called()
```

**Existing test to REPLACE** (from `test_adapter.py` lines 45–55):
```python
    @pytest.mark.asyncio
    async def test_detect_resolution_returns_none(self) -> None:
        """Phase 6 stub — detect_resolution always returns None."""
        from uuid import uuid4
        from unittest.mock import AsyncMock
        adapter = PolymarketAdapter()
        session = AsyncMock()
        result = await adapter.detect_resolution(session, uuid4())
        assert result is None
```
This test in `test_adapter.py` must be REPLACED (not just supplemented) — the stub behavior is no longer correct after Phase 7.

**Integration test marks** (from `test_tasks.py` lines 136–139):
```python
_integration_marks = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]
```

---

### `backend/tests/settlement/test_force_settle.py` (test)

**Analog:** `backend/tests/settlement/test_settlement_router.py` (lines 1–254)

**Test file header + marks** (lines 1–38):
```python
from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4
import httpx
import pytest

from app.auth.deps import current_active_admin
from app.main import app
from app.settlement.router import get_market_resolver

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]
```

**Dependency override helpers** (lines 150–155):
```python
def _admin(user_id: UUID) -> None:
    app.dependency_overrides[current_active_admin] = lambda: _Admin(user_id)

def _resolver(r: FakeMarketResolver) -> None:
    app.dependency_overrides[get_market_resolver] = lambda: r
```

**ASGI client fixture** (lines 61–64):
```python
@pytest_asyncio.fixture(loop_scope="session")
async def api() -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

**Admin auth pattern** (lines 91–95):
```python
class _Admin:
    def __init__(self, user_id: UUID) -> None:
        self.id = user_id
```

**401 guard test pattern** (lines 161–167):
```python
async def test_resolve_requires_admin(api: httpx.AsyncClient) -> None:
    """No admin Bearer -> 401 (the real current_active_admin gate, no override)."""
    r = await api.post(
        f"/admin/markets/{uuid4()}/resolve",
        json={"winning_outcome_id": str(uuid4()), "justification": "x"},
    )
    assert r.status_code == 401
```

**GammaClient mock for force-settle audit snapshot:** The test must mock `GammaClient.fetch_market_by_id` to return a fake `umaResolutionStatus`. Use `unittest.mock.patch` on the import path in `settlement/router.py`.

---

## Shared Patterns

### `from __future__ import annotations` Rule
**Source:** `backend/app/settlement/router.py` line 17 (docstring comment)
**Apply to:** ALL files being modified/created in this phase

| File | Has `from __future__ import annotations`? | Correct? |
|------|--------------------------------------------|----------|
| `alembic/versions/0007...py` | YES (copy from analog) | OK — not a FastAPI file |
| `config.py` | YES (line 1) | OK |
| `adapter.py` | YES (line 1) | OK |
| `tasks.py` | YES (line 1) | OK |
| `celery_app.py` | YES (line 1) | OK |
| `models.py` | YES (line 1) | OK |
| `router.py` | ABSENT (intentional) | MUST remain absent |
| `test_detect_resolution.py` | YES (convention) | OK |
| `test_force_settle.py` | YES (line 1 of analog) | OK |

### Admin Bearer Authentication
**Source:** `backend/app/settlement/router.py` lines 27, 57
**Apply to:** `settlement/router.py` force-settle endpoint
```python
from app.auth.deps import current_active_admin
from app.auth.models import User

admin: Annotated[User, Depends(current_active_admin)]
```

### Structlog Event Logging
**Source:** `backend/app/integrations/polymarket/tasks.py` lines 31, 69, 96
**Apply to:** `tasks.py` new detect task, `adapter.py` detect_resolution
```python
log = structlog.get_logger()
log.info("poll_complete", market_count=market_count)
log.error("poll_failed", error=str(exc))
log.warning("gamma.parse_failed", raw_id=raw.get("id"))
```

### Sentry Exception Capture
**Source:** `backend/app/integrations/polymarket/tasks.py` lines 17, 96
**Apply to:** `tasks.py` new detect task exception handler
```python
import sentry_sdk
sentry_sdk.capture_exception(exc)
```

### `session.rollback()` Before Service Call
**Source:** `backend/app/settlement/router.py` lines 65–66
**Apply to:** force-settle endpoint handler
```python
admin_id = admin.id
await session.rollback()
```
Must capture `admin.id` as a plain value BEFORE the rollback/service call to avoid `MissingGreenlet` on the session-expired admin object.

### Beat Schedule Entry Format
**Source:** `backend/app/celery_app.py` lines 48–58
**Apply to:** `celery_app.py` beat_schedule addition
```python
"detect-polymarket-resolutions": {
    "task": "app.integrations.polymarket.tasks.detect_polymarket_resolutions",
    "schedule": 60.0,
},
```

---

## No Analog Found

All 9 files have close analogs in the codebase. No file requires falling back to RESEARCH.md patterns alone.

---

## Implementation Notes

### Grace-Period Conditional Update (Pitfall 2)
The Beat task must use a conditional DB update to set `uma_resolved_at` only when NULL, to handle Celery at-least-once delivery races:
```python
# From RESEARCH.md Pattern 1 — use conditional UPDATE, not simple assignment
if market.uma_resolved_at is None:
    market.uma_resolved_at = datetime.now(UTC)
    await session.flush()
    continue  # Start the clock; settle on next tick
```
The `SettlementService.resolve_market` idempotency guard (`WHERE bets.status = PENDING`) provides a second safety net.

### `selectinload(Market.outcomes)` Required (Pitfall 3)
Every query that accesses `market.outcomes` in the Beat task MUST use `selectinload(Market.outcomes)`. The relationship has `lazy="raise"` (models.py line 107), so any access without eager loading raises `MissingGreenlet`.

### Audit Row Transaction Boundary (Assumption A1)
`SettlementService.resolve_market` internally uses `async with session.begin()` which commits. The `polymarket_admin_override` audit row must go in a SEPARATE `async with session.begin()` block AFTER `resolve_market` returns. Do NOT call `AuditService.record` inside the same `session.begin()` that `resolve_market` owns.

---

## Metadata

**Analog search scope:** `backend/alembic/versions/`, `backend/app/integrations/polymarket/`, `backend/app/settlement/`, `backend/app/core/`, `backend/app/markets/`, `backend/app/celery_app.py`, `backend/tests/polymarket/`, `backend/tests/settlement/`
**Files scanned:** 17
**Pattern extraction date:** 2026-05-28
