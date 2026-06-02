# Phase 6: Polymarket Sync (Catalog Replication) - Pattern Map

**Mapped:** 2026-05-28
**Files analyzed:** 17 new/modified files
**Analogs found:** 15 / 17

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/app/integrations/polymarket/__init__.py` | config | module-init | `backend/app/integrations/__init__.py` | exact |
| `backend/app/integrations/polymarket/client.py` | service | request-response | `backend/app/db/session.py` (singleton factory) | role-match |
| `backend/app/integrations/polymarket/schemas.py` | model | transform | `backend/app/markets/schemas.py` (Pydantic v2) | role-match |
| `backend/app/integrations/polymarket/adapter.py` | service | CRUD | `backend/app/integrations/market_source.py` (HouseAdapter) | exact |
| `backend/app/integrations/polymarket/tasks.py` | service | event-driven | `backend/app/celery_app.py` (task patterns) | role-match |
| `backend/app/markets/router.py` (modify) | controller | request-response | self (existing public endpoint) | exact |
| `backend/app/markets/service.py` (modify) | service | CRUD | self (existing list_markets) | exact |
| `backend/app/markets/models.py` (modify) | model | CRUD | self (existing Market columns) | exact |
| `backend/app/markets/schemas.py` (modify) | model | transform | self (existing MarketListItem) | exact |
| `backend/app/core/config.py` (modify) | config | -- | self (existing Settings) | exact |
| `backend/app/celery_app.py` (modify) | config | event-driven | self (existing beat_schedule) | exact |
| `backend/alembic/versions/0004_*.py` | migration | batch | `backend/alembic/versions/0003_phase4_markets.py` | exact |
| `frontend/src/components/market-card.tsx` | component | request-response | `frontend/src/app/(auth)/login/login-form.tsx` | partial |
| `frontend/src/components/source-badge.tsx` | component | request-response | `frontend/src/components/ui/card.tsx` (shadcn primitive) | partial |
| `frontend/src/components/odds-display.tsx` | component | request-response | `frontend/src/components/ui/card.tsx` (shadcn primitive) | partial |
| `frontend/src/components/market-list.tsx` | component | request-response | `frontend/src/app/page.tsx` (Server Component) | role-match |
| `frontend/src/components/market-list-skeleton.tsx` | component | request-response | -- | no-analog |

---

## Pattern Assignments

### `backend/app/integrations/polymarket/__init__.py` (config, module-init)

**Analog:** `backend/app/integrations/__init__.py`

**Full pattern** (lines 1-16):
```python
from app.integrations.market_source import (
    REGISTRY,
    HouseAdapter,
    MarketSource,
    get_adapter,
    register_source,
)

__all__ = [
    "REGISTRY",
    "HouseAdapter",
    "MarketSource",
    "get_adapter",
    "register_source",
]
```

**Apply:** New `__init__.py` should import `PolymarketAdapter` and call `register_source(MarketSourceEnum.POLYMARKET, PolymarketAdapter())` following the exact pattern of `market_source.py` line 86:
```python
register_source(MarketSourceEnum.HOUSE, HouseAdapter())
```

---

### `backend/app/integrations/polymarket/client.py` (service, request-response)

**Analog:** `backend/app/db/session.py` (lazy singleton with `@lru_cache`)

**Singleton factory pattern** (lines 23-39):
```python
@lru_cache(maxsize=1)
def _get_engine() -> AsyncEngine:
    settings = Settings()
    return create_async_engine(
        str(settings.DATABASE_URL),
        pool_size=10,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=settings.is_dev,
    )
```

**Apply:** `GammaClient` should follow the lazy-init singleton pattern. The `_get_client()` method in RESEARCH.md Pattern 1 already mirrors this: create `httpx.AsyncClient` lazily, re-create if closed.

**Imports pattern** -- project conventions:
```python
from __future__ import annotations

import structlog
from app.core.config import get_settings
```

**Error handling pattern** -- from `celery_app.py` lines 112-131 (Sentry capture):
```python
import sentry_sdk
sentry_sdk.capture_exception(exception)
```

---

### `backend/app/integrations/polymarket/schemas.py` (model, transform)

**Analog:** `backend/app/markets/schemas.py`

**Pydantic v2 model_config pattern** (lines 66-68, 80-81, 100-101):
```python
class OutcomeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
```

**field_validator pattern** (lines 38-46):
```python
@field_validator("deadline")
@classmethod
def deadline_must_be_future(cls, v: datetime) -> datetime:
    if v.tzinfo is None:
        v = v.replace(tzinfo=UTC)
    if v <= datetime.now(UTC):
        raise ValueError("Deadline must be in the future")
    return v
```

**field_serializer pattern** (lines 74-77):
```python
@field_serializer("initial_odds", "current_odds")
@classmethod
def serialize_decimal(cls, v: Decimal) -> str:
    return str(v)
```

**Apply:** `GammaMarket` Pydantic model uses `field_validator(mode="before")` for stringified JSON parsing + `model_validator(mode="after")` for `_derive_status`. The project uses `from __future__ import annotations` at top, `ConfigDict` for model config.

**ENVIRONMENT toggle pattern** -- from `backend/app/core/config.py` lines 76-78:
```python
@property
def is_dev(self) -> bool:
    return self.ENVIRONMENT == "dev"
```

---

### `backend/app/integrations/polymarket/adapter.py` (service, CRUD)

**Analog:** `backend/app/integrations/market_source.py` -- `HouseAdapter` (lines 51-86)

**Protocol implementation pattern** (lines 51-86):
```python
class HouseAdapter:
    async def fetch_active_markets(
        self, session: AsyncSession, *, limit: int = 25,
    ) -> list[Market]:
        stmt = (
            select(Market)
            .where(Market.status == MarketStatus.OPEN.value)
            .where(Market.source == MarketSourceEnum.HOUSE.value)
            .options(selectinload(Market.outcomes))
            .order_by(Market.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def fetch_market(
        self, session: AsyncSession, market_id: UUID,
    ) -> Market | None:
        stmt = (
            select(Market)
            .where(Market.id == market_id)
            .options(
                selectinload(Market.outcomes),
                selectinload(Market.odds_snapshots),
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def detect_resolution(
        self, session: AsyncSession, market_id: UUID,
    ) -> ResolutionResult | None:
        return None
```

**Registration pattern** (line 86):
```python
register_source(MarketSourceEnum.HOUSE, HouseAdapter())
```

**Protocol definition** (lines 23-34):
```python
@runtime_checkable
class MarketSource(Protocol):
    async def fetch_active_markets(
        self, session: AsyncSession, *, limit: int = 25,
    ) -> list[Market]: ...

    async def fetch_market(
        self, session: AsyncSession, market_id: UUID,
    ) -> Market | None: ...

    async def detect_resolution(
        self, session: AsyncSession, market_id: UUID,
    ) -> ResolutionResult | None: ...
```

**Apply:** `PolymarketAdapter` must implement all three methods with identical signatures. `detect_resolution` returns `None` in Phase 6 (Phase 7 adds real resolution). The adapter uses `selectinload(Market.outcomes)` for eager loading, consistent with `HouseAdapter`.

**Audit logging pattern** -- from `backend/app/markets/service.py` lines 76-87:
```python
await AuditService.record(
    session,
    actor=f"user:{admin_user.id}",
    event_type="market.created",
    payload={
        "market_id": str(market.id),
        "question": body.question,
        "source": "HOUSE",
    },
    ip=ip,
)
```

---

### `backend/app/integrations/polymarket/tasks.py` (service, event-driven)

**Analog:** `backend/app/celery_app.py`

**Celery app import + task decorator pattern** (lines 37-41, 133-140):
```python
celery_app = Celery(
    "xpredict",
    broker=str(settings.REDIS_URL),
    backend=str(settings.REDIS_URL),
)

@celery_app.task(name="app.core.sentry.sentry_test_task")
def sentry_test_task() -> None:
    raise RuntimeError("sentry test from worker")
```

**Beat schedule registration pattern** (line 44):
```python
celery_app.conf.beat_schedule = {}  # Phases 2-9 append tasks here
```

**structlog context binding pattern** (lines 97-104):
```python
structlog.contextvars.clear_contextvars()
if task is not None:
    structlog.contextvars.bind_contextvars(
        task_id=task_id,
        task_name=task.name,
    )
```

**Apply:** Tasks import `celery_app` from `app.celery_app`, use `@celery_app.task(name="...")` decorator. Beat entries appended to `beat_schedule` dict in `celery_app.py`. structlog for logging within tasks.

---

### `backend/app/markets/router.py` (modify -- controller, request-response)

**Analog:** self -- existing public market list endpoint (lines 131-148)

**Public endpoint pattern** (lines 131-148):
```python
public_market_router = APIRouter(
    prefix="/api/v1/markets",
    tags=["markets"],
)

@public_market_router.get("", response_model=PaginatedResponse[MarketListItem])
async def list_markets_public(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse[MarketListItem]:
    items, total = await MarketService.list_markets(
        session,
        page=page,
        page_size=page_size,
        status=MarketStatus.OPEN.value,
    )
    return paginated_response(
        [MarketListItem.model_validate(m) for m in items],
        total,
        page,
        page_size,
    )
```

**Apply:** Modify `list_markets_public` to call a new service method (`list_home_markets`) that returns house-first + Polymarket-by-volume. The response schema (`MarketListItem`) needs `volume` and `source_url` fields added.

---

### `backend/app/markets/service.py` (modify -- service, CRUD)

**Analog:** self -- existing `list_markets` (lines 187-214)

**Query pattern with selectinload** (lines 196-214):
```python
base = select(Market)
if source:
    base = base.where(Market.source == source)
if status:
    base = base.where(Market.status == status)

items_stmt = (
    base.options(selectinload(Market.outcomes))
    .order_by(Market.created_at.desc())
    .offset((page - 1) * page_size)
    .limit(page_size)
)
result = await session.execute(items_stmt)
return list(result.scalars().all()), total
```

**Apply:** Add `list_home_markets()` method using two queries concatenated (RESEARCH Pattern 5): house markets by `created_at desc`, then Polymarket by `volume_24hr desc` with `limit(25)`.

---

### `backend/app/markets/models.py` (modify -- model, CRUD)

**Analog:** self -- existing column conventions

**Column declaration pattern** (lines 60-65):
```python
source_market_id: Mapped[str | None] = mapped_column(
    String(200), nullable=True,
)
condition_id: Mapped[str | None] = mapped_column(
    String(200), nullable=True,
)
```

**Money column pattern** -- from `backend/app/db/types.py` (lines 1-21):
```python
from app.db.types import Money
# Usage:
volume: Mapped[Money] = mapped_column()
```

**Apply:** Add `volume: Mapped[Money]` and `volume_24hr: Mapped[Money]` columns using the `Money` alias (`Numeric(18, 4)`). Add nullable `source_url: Mapped[str | None] = mapped_column(Text, nullable=True)` if adding a column (or derive in schema per RESEARCH OQ#3).

---

### `backend/app/markets/schemas.py` (modify -- model, transform)

**Analog:** self -- existing `MarketListItem` (lines 100-113)

**Response schema pattern** (lines 100-113):
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
    outcomes: list[OutcomeRead]
```

**Apply:** Add `volume: Decimal`, `volume_24hr: Decimal`, and optionally a computed `source_url: str | None` property to `MarketListItem`. Serialize Decimals as strings using the existing `field_serializer` pattern.

---

### `backend/app/core/config.py` (modify -- config)

**Analog:** self -- existing Settings env var pattern (lines 44-73)

**Settings field pattern** (lines 44-73):
```python
# Phase 2 — Auth & Identity (AUTH-01..09, D-09, RESEARCH §Runtime State)
SECRET_KEY: str = Field(min_length=32)
JWT_ALGORITHM: Literal["HS256"] = "HS256"
ACCESS_TOKEN_LIFETIME_SECONDS: int = 900
```

**Apply:** Add Phase 6 settings block:
```python
# Phase 6 — Polymarket Sync
GAMMA_API_BASE_URL: str = "https://gamma-api.polymarket.com"
POLYMARKET_POLL_INTERVAL_SECONDS: int = 30
POLYMARKET_SNAPSHOT_INTERVAL_SECONDS: int = 300
POLYMARKET_LOCK_TTL_SECONDS: int = 25
```

---

### `backend/alembic/versions/0004_*.py` (migration, batch)

**Analog:** `backend/alembic/versions/0003_phase4_markets.py`

**Migration header pattern** (lines 1-27):
```python
"""Phase 4 markets: markets + outcomes + odds_snapshots.

Revision ID: 0003_phase4_markets
Revises: 0002_phase2_auth
Create Date: 2026-05-27
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_phase4_markets"
down_revision: str | None = "0002_phase2_auth"
branch_labels: str | None = None
depends_on: str | None = None

TENANT_DEFAULT = "00000000-0000-0000-0000-000000000001"
```

**Column add pattern** -- this is an ALTER TABLE migration (no full table creation). Use `op.add_column()`:
```python
def upgrade() -> None:
    op.add_column("markets", sa.Column("volume", sa.Numeric(18, 4), nullable=False, server_default=sa.text("0")))
    op.add_column("markets", sa.Column("volume_24hr", sa.Numeric(18, 4), nullable=False, server_default=sa.text("0")))
    op.create_index(
        "ix_markets_source_source_market_id",
        "markets",
        ["source", "source_market_id"],
        unique=True,
        postgresql_where=sa.text("source_market_id IS NOT NULL"),
    )
```

**Apply:** Revision `0004_phase6_polymarket_sync`, down_revision `0003_phase4_markets`. Add `volume`, `volume_24hr` columns + partial unique index on `(source, source_market_id)`.

---

### `frontend/src/components/market-card.tsx` (component, request-response)

**Analog:** `frontend/src/components/ui/card.tsx` (shadcn Card) + `frontend/src/app/(auth)/login/login-form.tsx` (component structure)

**shadcn Card import pattern** (card.tsx lines 84-90):
```tsx
export {
  Card,
  CardHeader,
  CardFooter,
  CardTitle,
  CardDescription,
  CardContent,
};
```

**Component file structure** (login-form.tsx lines 1-13):
```tsx
/**
 * Plan 02-04 -- Player login form (client component).
 */
"use client";

import { useActionState, startTransition } from "react";
// ...
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
```

**Apply:** MarketCard is a Server Component (no "use client"). Import `Card`, `CardHeader`, `CardContent`, `CardFooter` from `@/components/ui/card`. Use `cn()` from `@/lib/utils` for conditional class names. Use `Link` from `next/link` for market detail navigation.

---

### `frontend/src/components/source-badge.tsx` (component)

**Analog:** `frontend/src/components/ui/card.tsx` (shadcn primitive pattern)

**shadcn primitive pattern** (card.tsx lines 9-22):
```tsx
const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "rounded-lg border border-zinc-200 bg-white text-zinc-950 shadow-sm dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-50",
      className,
    )}
    {...props}
  />
));
Card.displayName = "Card";
```

**Apply:** SourceBadge is a simple functional component (no forwardRef needed since it is not a primitive). Import shadcn `Badge` component (to be installed). Conditionally render link for Polymarket source.

---

### `frontend/src/components/market-list.tsx` (component, Server Component)

**Analog:** `frontend/src/app/page.tsx` (Server Component pattern)

**Server Component pattern** (page.tsx full file):
```tsx
export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 px-6 py-24 text-center">
      <h1 className="text-4xl font-semibold tracking-tight">XPredict</h1>
      <p className="text-base text-zinc-600 dark:text-zinc-400">
        Phase 1 &mdash; scaffold OK
      </p>
    </main>
  );
}
```

**Apply:** MarketList is an async Server Component that fetches from the internal API (`/api/v1/markets`) and renders a responsive grid of `MarketCard` components. `page.tsx` will be modified to import and render `MarketList`.

---

### `backend/tests/polymarket/conftest.py` (test config)

**Analog:** `backend/tests/markets/conftest.py`

**Test fixture pattern** (conftest.py lines 31-52):
```python
@pytest_asyncio.fixture(loop_scope="session")
async def admin_user(async_session: AsyncSession) -> AsyncGenerator[User, None]:
    from sqlalchemy import delete
    from app.auth.models import User

    user = User(
        email="market-admin@test.com",
        hashed_password="not-a-real-hash",
        is_active=True,
        is_superuser=True,
        is_verified=True,
        display_name="Market Admin",
    )
    async_session.add(user)
    await async_session.flush()
    try:
        yield user
    finally:
        await async_session.execute(delete(User).where(User.id == user.id))
        await async_session.flush()
```

**Sample market fixture pattern** (conftest.py lines 54-110):
```python
@pytest_asyncio.fixture(loop_scope="session")
async def sample_market(async_session: AsyncSession) -> AsyncGenerator[Market, None]:
    from sqlalchemy import delete
    from app.markets.enums import MarketSourceEnum, MarketStatus
    from app.markets.models import Market, OddsSnapshot, Outcome, generate_slug

    market = Market(
        question="Will it rain tomorrow?",
        slug=generate_slug("Will it rain tomorrow?"),
        resolution_criteria="Rain recorded at station X by 23:59 UTC",
        category="weather",
        source=MarketSourceEnum.HOUSE.value,
        status=MarketStatus.OPEN.value,
        deadline=datetime.now(UTC) + timedelta(days=1),
    )
    async_session.add(market)
    await async_session.flush()
    # ... outcomes + snapshots ...
    try:
        yield market
    finally:
        # cleanup in reverse FK order
```

**Apply:** New conftest needs: (1) sample Polymarket market fixture (source=POLYMARKET, with source_market_id and condition_id), (2) mock GammaClient fixture, (3) VCR JSON fixture loader, (4) fake_redis from global conftest.

---

### `backend/tests/polymarket/test_schemas.py` (test, unit)

**Analog:** `backend/tests/markets/test_service.py` (Pydantic validation tests)

**Schema validation test pattern** (test_service.py lines 18-71):
```python
class TestMarketCreateSchema:
    def test_rejects_past_deadline(self):
        with pytest.raises(ValueError, match="future"):
            MarketCreate(
                question="test",
                resolution_criteria="test",
                deadline=datetime.now(UTC) - timedelta(hours=1),
            )

    def test_accepts_valid_create(self):
        body = MarketCreate(
            question="Will it rain?",
            resolution_criteria="Rain at station X",
            deadline=datetime.now(UTC) + timedelta(days=1),
            initial_odds_yes=Decimal("0.7"),
            category="weather",
        )
        assert body.initial_odds_yes == Decimal("0.7")
```

**Apply:** Test `GammaMarket` parser with VCR fixture JSON. Test stringified JSON field parsing, Decimal conversion, `_derive_status` state machine with all 4 fixture files.

---

### `backend/tests/polymarket/test_adapter.py` (test, integration)

**Analog:** `backend/tests/markets/test_protocol.py`

**Protocol conformance test pattern** (test_protocol.py full file):
```python
pytestmark = [pytest.mark.integration]
_async = pytest.mark.asyncio(loop_scope="session")

class TestProtocolConformance:
    def test_house_adapter_isinstance(self):
        adapter = HouseAdapter()
        assert isinstance(adapter, MarketSource)

    def test_registry_lookup(self):
        adapter = get_adapter(MarketSourceEnum.HOUSE)
        assert isinstance(adapter, HouseAdapter)
        assert isinstance(adapter, MarketSource)

@_async
class TestHouseAdapter:
    async def test_fetch_active_markets(self, async_session, sample_market):
        adapter = HouseAdapter()
        markets = await adapter.fetch_active_markets(async_session)
        assert len(markets) >= 1
```

**Apply:** Mirror exactly for `PolymarketAdapter`: `isinstance(adapter, MarketSource)` check, registry lookup via `get_adapter(MarketSourceEnum.POLYMARKET)`, and async method tests with DB session.

---

### `frontend/src/app/(auth)/__tests__/login.test.tsx` (test, frontend)

**Analog:** self -- vitest + testing-library pattern

**Frontend test pattern** (login.test.tsx lines 1-40):
```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock module
const loginActionMock = vi.hoisted(() =>
  vi.fn<(...args: unknown[]) => Promise<unknown>>(async () => undefined),
);
vi.mock("@/lib/auth", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth")>("@/lib/auth");
  return { ...actual, loginAction: loginActionMock };
});

describe("<LoginForm />", () => {
  it("renders email + password inputs and a Sign in button", () => {
    render(<LoginForm />);
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
  });
});
```

**Apply:** MarketCard tests render the component with mock market data, assert question text, odds display, source badge presence/text.

---

## Shared Patterns

### Imports Convention
**Source:** All backend files
**Apply to:** All new backend files
```python
from __future__ import annotations
# stdlib imports
# third-party imports
# project imports from app.*
```

### structlog Logging
**Source:** `backend/app/celery_app.py` lines 99-104
**Apply to:** `client.py`, `adapter.py`, `tasks.py`
```python
import structlog
log = structlog.get_logger()
```

### Audit Logging
**Source:** `backend/app/core/audit/service.py` lines 24-58
**Apply to:** `adapter.py` (market sync events)
```python
await AuditService.record(
    session,
    actor="system:polymarket-sync",
    event_type="market.synced",
    payload={...},
)
```

### Money / Decimal Convention
**Source:** `backend/app/db/types.py` lines 1-21
**Apply to:** `models.py` (new volume columns), `schemas.py` (GammaMarket Decimal parsing)
```python
from app.db.types import Money
# Column:
volume: Mapped[Money] = mapped_column()
# Or for nullable:
volume: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
```

### Async Session Pattern
**Source:** `backend/app/db/session.py` lines 51-59
**Apply to:** `adapter.py`, `tasks.py` (wherever DB access is needed)
```python
from app.db.session import get_async_session
# In FastAPI deps:
session: Annotated[AsyncSession, Depends(get_async_session)]
# In Celery tasks (outside request context):
# Use async_sessionmaker directly
```

### UUID PK + tenant_id Ghost Column
**Source:** `backend/app/markets/models.py` lines 46-92
**Apply to:** Any new ORM models (none expected in Phase 6, but keep consistent)
```python
id: Mapped[PyUUID] = mapped_column(
    UUID(as_uuid=True),
    primary_key=True,
    default=uuid4,
    server_default=func.gen_random_uuid(),
)
tenant_id: Mapped[PyUUID | None] = mapped_column(
    UUID(as_uuid=True),
    nullable=True,
    default=lambda: get_settings().TENANT_ID_DEFAULT,
)
```

### Test Markers
**Source:** `backend/tests/markets/test_protocol.py` lines 1-14
**Apply to:** All new backend test files
```python
pytestmark = [pytest.mark.integration]
_async = pytest.mark.asyncio(loop_scope="session")
```

### Frontend cn() Utility
**Source:** `frontend/src/lib/utils.ts` lines 10-15
**Apply to:** All new frontend components
```tsx
import { cn } from "@/lib/utils";
// Usage: className={cn("base-class", condition && "conditional-class")}
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `frontend/src/components/market-list-skeleton.tsx` | component | request-response | No skeleton/loading component exists yet; shadcn `Skeleton` primitive to be installed; use RESEARCH.md patterns |

---

## Metadata

**Analog search scope:** `backend/app/`, `backend/tests/`, `backend/alembic/`, `frontend/src/`
**Files scanned:** 45+ (glob + targeted reads)
**Pattern extraction date:** 2026-05-28
