# Phase 4: Markets Domain & HouseAdapter - Pattern Map

**Mapped:** 2026-05-27
**Files analyzed:** 9 new files + 2 modified files
**Analogs found:** 9 / 9

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/app/markets/models.py` | model | CRUD | `backend/app/auth/models.py` | role-match |
| `backend/app/markets/schemas.py` | schema | request-response | `backend/app/auth/schemas.py` | role-match |
| `backend/app/markets/router.py` | route | request-response | `backend/app/auth/router.py` | role-match |
| `backend/app/markets/admin_router.py` | route | request-response | `backend/app/auth/admin_router.py` | exact |
| `backend/app/markets/service.py` | service | CRUD | `backend/app/core/audit/service.py` | role-match |
| `backend/app/integrations/market_source.py` | utility | request-response | `backend/app/auth/admin_router.py` (registry pattern) | partial |
| `backend/alembic/versions/0003_phase4_markets.py` | migration | CRUD | `backend/alembic/versions/0002_phase2_auth.py` | exact |
| `backend/tests/markets/conftest.py` | test | request-response | `backend/tests/auth/conftest.py` | exact |
| `backend/tests/markets/test_admin_router.py` | test | request-response | `backend/tests/auth/test_admin_bearer.py` | exact |
| `backend/app/main.py` (modified) | config | request-response | itself (lines 135-136) | exact |
| `backend/alembic/env.py` (modified) | config | CRUD | itself (lines 26-29) | exact |

---

## Pattern Assignments

### `backend/app/markets/models.py` (model, CRUD)

**Analog:** `backend/app/auth/models.py` + `backend/app/core/audit/models.py`

**Imports pattern** (`auth/models.py` lines 20-33, `audit/models.py` lines 8-19):
```python
from __future__ import annotations  # OK in model files — not routers

from datetime import datetime
from decimal import Decimal
from uuid import UUID as PyUUID, uuid4

import sqlalchemy as sa
from sqlalchemy import DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.db.base import Base
```

**UUID PK pattern** (`auth/models.py` lines 91-96):
```python
id: Mapped[PyUUID] = mapped_column(
    UUID(as_uuid=True),
    primary_key=True,
    default=uuid4,                           # Python-side default (WR-05)
    server_default=func.gen_random_uuid(),   # raw SQL inserts
)
```

**Tenant ID ghost column pattern** (`auth/models.py` lines 67-71, `audit/models.py` lines 47-51):
```python
tenant_id: Mapped[PyUUID | None] = mapped_column(
    UUID(as_uuid=True),
    nullable=True,
    default=lambda: get_settings().TENANT_ID_DEFAULT,
)
```

**Timestamp column pattern** (`auth/models.py` lines 123-127):
```python
created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    nullable=False,
)
```

**Integer column with server_default** (`auth/models.py` lines 62-63):
```python
token_version: Mapped[int] = mapped_column(
    Integer, nullable=False, server_default="0", default=0,
)
```

**Relationship with cascade** (`auth/models.py` lines 75-77):
```python
refresh_tokens: Mapped[list[RefreshToken]] = relationship(
    back_populates="user", cascade="all, delete-orphan",
)
```

**FK column pattern** (`auth/models.py` lines 100-105):
```python
user_id: Mapped[PyUUID] = mapped_column(
    UUID(as_uuid=True),
    ForeignKey("users.id", ondelete="CASCADE"),
    nullable=False,
    index=True,
)
```

**New for Phase 4 — `__table_args__` with CheckConstraints** (from RESEARCH.md Pattern 2):
```python
__table_args__ = (
    sa.CheckConstraint(
        "status IN ('DRAFT', 'OPEN', 'CLOSED', 'RESOLVED', 'CANCELLED')",
        name="ck_markets_status",
    ),
    sa.CheckConstraint(
        "source IN ('HOUSE', 'POLYMARKET')",
        name="ck_markets_source",
    ),
)
```

**New for Phase 4 — lazy="raise" on async relationships** (RESEARCH.md Pitfall 2):
```python
outcomes: Mapped[list["Outcome"]] = relationship(
    back_populates="market", cascade="all, delete-orphan", lazy="raise",
)
```

---

### `backend/app/markets/schemas.py` (schema, request-response)

**Analog:** `backend/app/auth/schemas.py`

**Imports pattern** (`auth/schemas.py` lines 1-19):
```python
from __future__ import annotations  # OK in schema files

import uuid
from pydantic import Field, computed_field
# Phase 4 will also need:
from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel, ConfigDict
```

**Schema with `from_attributes` pattern** (`auth/schemas.py` lines 21-35) — note Phase 4 schemas are plain `BaseModel`, not `schemas.BaseUser`:
```python
class MarketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question: str
    slug: str
    # ... other fields
```

**Field exclusion / alias pattern** (`auth/schemas.py` lines 29-35):
```python
is_superuser: bool = Field(default=False, exclude=True)

@computed_field
@property
def is_admin(self) -> bool:
    return self.is_superuser
```

**New for Phase 4 — Decimal serialization** (RESEARCH.md Pitfall 3): odds fields must serialize as string, not float:
```python
from pydantic import field_serializer

class OutcomeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    current_odds: Decimal

    @field_serializer("current_odds", "initial_odds")
    def serialize_odds(self, value: Decimal) -> str:
        return str(value)
```

**New for Phase 4 — pagination schemas** (RESEARCH.md Pattern 4):
```python
from typing import Generic, TypeVar
T = TypeVar("T")

class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int
```

---

### `backend/app/markets/router.py` (route, request-response — public surface)

**Analog:** `backend/app/auth/router.py`

**Critical deviation:** NO `from __future__ import annotations` — `admin_router.py` line 43-47 documents this. Breaks `Annotated[T, Depends(...)]` resolution in FastAPI.

**Module-level APIRouter pattern** (`auth/router.py` lines 105-106):
```python
# NO from __future__ import annotations
from typing import Annotated
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_async_session

public_market_router = APIRouter(
    prefix="/api/v1/markets",
    tags=["markets"],
    # No auth dependencies — public read-only
)
```

**Route handler signature pattern** (`auth/router.py` lines 114-139):
```python
@public_market_router.get("")
async def list_markets(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse[MarketRead]:
    ...
```

**HTTPException with detail dict pattern** (`auth/router.py` lines 126-131):
```python
raise HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail={
        "code": "MARKET_NOT_FOUND",
        "reason": "Market does not exist or is not open",
    },
)
```

---

### `backend/app/markets/admin_router.py` (route, request-response — admin surface)

**Analog:** `backend/app/auth/admin_router.py`

**Critical deviation:** NO `from __future__ import annotations` (documented in `admin_router.py` lines 43-47).

**Imports pattern** (`admin_router.py` lines 51-65):
```python
# NO from __future__ import annotations
from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.admin_router import current_active_admin
from app.auth.models import User
from app.db.session import get_async_session
```

**Admin router with auth dependency on all routes** (`admin_router.py` lines 121-122, RESEARCH.md admin router pattern):
```python
admin_market_router = APIRouter(
    prefix="/api/v1/admin/markets",
    tags=["admin-markets"],
    dependencies=[Depends(current_active_admin)],  # ALL routes require admin
)
```

**Route with explicit admin dep for actor attribution** (`admin_router.py` lines 124-130):
```python
@admin_market_router.post("", status_code=status.HTTP_201_CREATED)
async def create_market(
    request: Request,
    body: MarketCreate,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
) -> MarketRead:
    ...
```

**AuditService call pattern** (`admin_router.py` lines 168-178):
```python
await AuditService.record(
    session,
    actor=f"user:{admin.id}",
    event_type="market.created",
    payload={"market_id": str(market.id), "question": market.question},
    ip=request.client.host if request.client else None,
)
await session.commit()
```

**HTTPException 423 Locked pattern** (RESEARCH.md Pattern 3):
```python
if market.bet_count > 0 and update_data.resolution_criteria is not None:
    raise HTTPException(
        status_code=423,
        detail={
            "code": "CRITERIA_LOCKED",
            "reason": "Resolution criteria cannot be changed after bets have been placed",
        },
    )
```

---

### `backend/app/markets/service.py` (service, CRUD)

**Analog:** `backend/app/core/audit/service.py`

**Service class pattern** (`audit/service.py` lines 24-58):
```python
from __future__ import annotations  # OK in service files (no Depends)
from sqlalchemy.ext.asyncio import AsyncSession

class MarketService:
    """Market business logic. Caller controls the transaction."""

    @staticmethod
    async def create_market(
        session: AsyncSession,
        *,
        data: "MarketCreate",
        actor_id: "UUID",
    ) -> "Market":
        ...
        session.add(market)
        await session.flush()
        return market
```

**Flush (not commit) pattern** (`audit/service.py` lines 56-58):
```python
session.add(row)
await session.flush()  # flush to get server-defaulted id; caller commits
return row
```

**New for Phase 4 — slug generation** (RESEARCH.md Pattern 5):
```python
from slugify import slugify
from uuid import uuid4

def _generate_slug(question: str) -> str:
    base = slugify(question, max_length=80)
    suffix = uuid4().hex[:4]
    return f"{base}-{suffix}"
```

**New for Phase 4 — eager loading in async context** (RESEARCH.md Pitfall 2):
```python
from sqlalchemy import select
from sqlalchemy.orm import selectinload

stmt = (
    select(Market)
    .options(selectinload(Market.outcomes))
    .where(Market.id == market_id)
)
result = await session.execute(stmt)
market = result.scalar_one_or_none()
```

---

### `backend/app/integrations/market_source.py` (utility, request-response)

**Analog:** No direct analog. Pattern comes from RESEARCH.md Pattern 1 (typing.Protocol) and the registry pattern implied by `admin_router.py`'s `current_active_admin` export style.

**Protocol definition pattern** (RESEARCH.md Pattern 1, Python docs):
```python
from __future__ import annotations  # OK — no Depends

from typing import Protocol, runtime_checkable
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

@runtime_checkable
class MarketSource(Protocol):
    async def fetch_active_markets(
        self, session: AsyncSession, *, limit: int = 25,
    ) -> list["Market"]: ...

    async def fetch_market(
        self, session: AsyncSession, market_id: UUID,
    ) -> "Market | None": ...

    async def detect_resolution(
        self, session: AsyncSession, market_id: UUID,
    ) -> None: ...
```

**Registry pattern** (RESEARCH.md Pattern 1):
```python
from app.markets.enums import MarketSourceEnum

REGISTRY: dict[MarketSourceEnum, MarketSource] = {}

def register_source(source: MarketSourceEnum, adapter: MarketSource) -> None:
    REGISTRY[source] = adapter

def get_adapter(source: MarketSourceEnum) -> MarketSource:
    try:
        return REGISTRY[source]
    except KeyError:
        raise ValueError(f"No adapter registered for source: {source!r}")
```

**HouseAdapter registration at module level** (mirrors `admin_router.py`'s `__all__` exports):
```python
class HouseAdapter:
    """Implements MarketSource via direct AsyncSession queries."""

    async def fetch_active_markets(
        self, session: AsyncSession, *, limit: int = 25,
    ) -> list[Market]:
        stmt = (
            select(Market)
            .options(selectinload(Market.outcomes))
            .where(Market.status == MarketStatus.OPEN)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def detect_resolution(
        self, session: AsyncSession, market_id: UUID,
    ) -> None:
        return None  # House markets resolve via explicit admin action (Phase 5)


# Module-level singleton registration
_house_adapter = HouseAdapter()
register_source(MarketSourceEnum.HOUSE, _house_adapter)
```

---

### `backend/alembic/versions/0003_phase4_markets.py` (migration, CRUD)

**Analog:** `backend/alembic/versions/0002_phase2_auth.py`

**File header pattern** (`0002_phase2_auth.py` lines 1-36):
```python
"""Phase 4 markets: markets + outcomes + odds_snapshots.

Revision ID: 0003_phase4_markets
Revises: 0002_phase2_auth
Create Date: 2026-05-27
...
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_phase4_markets"
down_revision: str | None = "0002_phase2_auth"
branch_labels: str | None = None
depends_on: str | None = None

TENANT_DEFAULT = "00000000-0000-0000-0000-000000000001"  # same literal as all migrations
```

**UUID PK column in migration** (`0002_phase2_auth.py` lines 44-50):
```python
sa.Column(
    "id",
    postgresql.UUID(as_uuid=True),
    primary_key=True,
    server_default=sa.text("gen_random_uuid()"),
),
```

**Tenant_id ghost column in migration** (`0002_phase2_auth.py` lines 84-88):
```python
sa.Column(
    "tenant_id",
    postgresql.UUID(as_uuid=True),
    nullable=True,
    server_default=sa.text(f"'{TENANT_DEFAULT}'::uuid"),
),
```

**CheckConstraint in op.create_table** (new for Phase 4 — String+CHECK pattern):
```python
sa.CheckConstraint(
    "status IN ('DRAFT', 'OPEN', 'CLOSED', 'RESOLVED', 'CANCELLED')",
    name="ck_markets_status",
),
```

**Index creation pattern** (`0002_phase2_auth.py` lines 135-143):
```python
op.create_index("ix_markets_slug", "markets", ["slug"], unique=True)
op.create_index("ix_outcomes_market_id", "outcomes", ["market_id"])
```

**FK column in migration** (`0002_phase2_auth.py` lines 107-110):
```python
sa.Column(
    "user_id",
    postgresql.UUID(as_uuid=True),
    sa.ForeignKey("users.id", ondelete="CASCADE"),
    nullable=False,
),
```

**Downgrade drop order: FK-bearing tables first** (`0002_phase2_auth.py` lines 146-161):
```python
def downgrade() -> None:
    # Drop FK-bearing tables first, then referenced tables
    op.drop_index("ix_odds_snapshots_market_id", table_name="odds_snapshots")
    op.drop_table("odds_snapshots")  # FK to outcomes + markets
    op.drop_index("ix_outcomes_market_id", table_name="outcomes")
    op.drop_table("outcomes")        # FK to markets
    op.drop_index("ix_markets_slug", table_name="markets")
    op.drop_table("markets")
```

---

### `backend/tests/markets/conftest.py` (test, request-response)

**Analog:** `backend/tests/auth/conftest.py`

**Phase env seed pattern** (`auth/conftest.py` lines 29-42):
```python
from __future__ import annotations
import os
import pytest
import pytest_asyncio

_PHASE4_TEST_ENV: dict[str, str] = {
    # No new required vars for Phase 4 beyond Phase 2's set.
    # python-slugify has no env config.
}
for _k, _v in _PHASE4_TEST_ENV.items():
    os.environ.setdefault(_k, _v)
```

**pytest_asyncio fixture with session scope + cleanup** (`auth/conftest.py` lines 69-99):
```python
@pytest_asyncio.fixture(loop_scope="session")
async def sample_market(async_session: AsyncSession) -> AsyncGenerator[Market, None]:
    from sqlalchemy import delete
    from app.markets.models import Market, Outcome

    market = Market(
        question="Will BTC hit $100k?",
        slug="will-btc-hit-100k-test1",
        resolution_criteria="Price on Binance closes above $100,000",
        source="HOUSE",
        status="OPEN",
        deadline=datetime(2026, 12, 31, tzinfo=timezone.utc),
    )
    async_session.add(market)
    await async_session.flush()
    # Add YES/NO outcomes
    yes = Outcome(market_id=market.id, label="YES", initial_odds=Decimal("0.5"), current_odds=Decimal("0.5"))
    no = Outcome(market_id=market.id, label="NO", initial_odds=Decimal("0.5"), current_odds=Decimal("0.5"))
    async_session.add_all([yes, no])
    await async_session.flush()
    try:
        yield market
    finally:
        await async_session.execute(delete(Market).where(Market.id == market.id))
        await async_session.flush()
```

---

### `backend/tests/markets/test_admin_router.py` (test, request-response)

**Analog:** `backend/tests/auth/test_admin_bearer.py`

**Test file header pattern** (`test_admin_bearer.py` lines 1-31):
```python
"""Admin market endpoint integration tests (ADM-01 through ADM-07)."""

from __future__ import annotations
from typing import TYPE_CHECKING
import pytest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]
```

**Inline ASGI client helper pattern** (`test_admin_bearer.py` lines 43-47):
```python
async def _client_for_app() -> httpx.AsyncClient:
    from app.main import app
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")
```

**Direct engine seed helper pattern** (`test_admin_bearer.py` lines 50-68):
```python
async def _seed_market(engine: AsyncEngine, slug: str = "test-market-seed") -> str:
    """INSERT a market row directly via engine (bypasses service layer)."""
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO markets (question, slug, resolution_criteria, "
                "source, status, deadline) "
                "VALUES (:q, :s, :rc, 'HOUSE', 'OPEN', NOW() + INTERVAL '7 days')"
            ),
            {"q": "Test question?", "s": slug, "rc": "Test criteria"},
        )
        await conn.commit()
    return slug
```

**Bearer auth header pattern** (`test_admin_bearer.py` lines 180-186):
```python
async with await _client_for_app() as client:
    resp = await client.get(
        "/api/v1/admin/markets",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
assert resp.status_code == 200
```

**Audit row verification pattern** (`test_admin_bearer.py` lines 296-316):
```python
async with engine.connect() as conn:
    rows = (
        await conn.execute(
            text(
                "SELECT actor, payload FROM audit_log "
                "WHERE event_type = 'market.created' "
                "ORDER BY occurred_at DESC LIMIT 1"
            ),
        )
    ).all()
assert len(rows) >= 1
```

---

## Shared Patterns

### Authentication (Admin Bearer)
**Source:** `backend/app/auth/admin_router.py` lines 88-93
**Apply to:** `admin_router.py` — import and use as router-level dependency
```python
from app.auth.admin_router import current_active_admin

admin_market_router = APIRouter(
    prefix="/api/v1/admin/markets",
    tags=["admin-markets"],
    dependencies=[Depends(current_active_admin)],
)
```

### Session Dependency
**Source:** `backend/app/db/session.py` lines 51-60
**Apply to:** All router files (`router.py`, `admin_router.py`)
```python
from app.db.session import get_async_session

session: Annotated[AsyncSession, Depends(get_async_session)]
```

### Audit Logging
**Source:** `backend/app/core/audit/service.py` lines 27-58
**Apply to:** All write operations in `admin_router.py` and `service.py`
```python
from app.core.audit.service import AuditService

await AuditService.record(
    session,
    actor=f"user:{admin.id}",
    event_type="market.created",   # or "market.updated", "market.closed"
    payload={"market_id": str(market.id), "slug": market.slug},
    ip=request.client.host if request.client else None,
)
# DO NOT commit here — caller (router) commits after this
```

### Error Handling (HTTPException with detail dict)
**Source:** `backend/app/auth/router.py` lines 126-131
**Apply to:** All router files
```python
raise HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail={
        "code": "MARKET_NOT_FOUND",
        "reason": "Market does not exist",
    },
)
```

### `from __future__ import annotations` exclusion rule
**Source:** `backend/app/auth/admin_router.py` lines 43-47
**Apply to:** `router.py`, `admin_router.py` — NEVER add this import to these files
**Allow in:** `models.py`, `schemas.py`, `service.py`, `market_source.py`, `conftest.py`, test files

### Transaction control (flush in service, commit in router)
**Source:** `backend/app/core/audit/service.py` lines 56-57
**Apply to:** `service.py` — flush only; `admin_router.py` — commit after service call + audit
```python
# In service.py:
session.add(market)
await session.flush()  # populates server-defaulted id/timestamps
return market

# In admin_router.py:
market = await MarketService.create_market(session, data=body, actor_id=admin.id)
await AuditService.record(session, actor=f"user:{admin.id}", event_type="market.created", ...)
await session.commit()  # single commit for market + audit atomically
```

### UUID PK with dual default
**Source:** `backend/app/core/audit/models.py` lines 27-33
**Apply to:** All new ORM models in `models.py`
```python
id: Mapped[PyUUID] = mapped_column(
    UUID(as_uuid=True),
    primary_key=True,
    default=uuid4,
    server_default=func.gen_random_uuid(),
)
```

### Tenant ID ghost column
**Source:** `backend/app/core/audit/models.py` lines 47-51
**Apply to:** All new ORM models (`Market`, `Outcome`, `OddsSnapshot`)
```python
tenant_id: Mapped[PyUUID | None] = mapped_column(
    UUID(as_uuid=True),
    nullable=True,
    default=lambda: get_settings().TENANT_ID_DEFAULT,
)
```

---

## Modified Files — Change Patterns

### `backend/app/main.py` (add router registration)
**Pattern source:** `main.py` lines 135-136
**Change:** Add two lines after `app.include_router(build_auth_routers())`:
```python
from app.markets.router import public_market_router
from app.markets.admin_router import admin_market_router

app.include_router(public_market_router)
app.include_router(admin_market_router)
```

### `backend/alembic/env.py` (register new models)
**Pattern source:** `alembic/env.py` lines 26-29
**Change:** Add one import line alongside existing model imports:
```python
from app.markets.models import Market, Outcome, OddsSnapshot  # noqa: F401  (Phase 4)
```

---

## No Analog Found

No files are fully novel — all have at least a partial analog. The `market_source.py` file uses `typing.Protocol` which has no prior use in this codebase, but the module-level registry pattern maps closely to how `admin_router.py` exports `current_active_admin` as a singleton dependency.

---

## Metadata

**Analog search scope:** `backend/app/auth/`, `backend/app/core/audit/`, `backend/alembic/versions/`, `backend/tests/auth/`, `backend/app/db/`, `backend/app/main.py`, `backend/alembic/env.py`
**Files scanned:** 11 source files read
**Pattern extraction date:** 2026-05-27
