# Phase 4: Markets Domain & HouseAdapter - Research

**Researched:** 2026-05-27
**Domain:** Market domain modeling, Protocol-based adapter pattern, admin CRUD API (SQLAlchemy 2.0 async + FastAPI + Postgres 16)
**Confidence:** HIGH

## Summary

Phase 4 establishes the source-agnostic market domain (Market, Outcome, OddsSnapshot) and proves the `MarketSource` Protocol with a fully-controllable `HouseAdapter`. The codebase already has a mature pattern for UUID PK models, tenant_id ghost columns, async sessions, admin Bearer auth, and audit logging -- Phase 4 follows these patterns verbatim and adds the market domain on top.

The core technical decisions are locked by CONTEXT.md: async Protocol methods returning ORM models, dict-based singleton registry, full lifecycle status enum (DRAFT/OPEN/CLOSED/RESOLVED/CANCELLED), Decimal(Numeric(8,6)) for odds probability 0-1, auto-generated slugs via python-slugify + UUID suffix, and offset-limit pagination. The research focus is therefore on implementation patterns rather than alternative exploration.

**Primary recommendation:** Use `typing.Protocol` with `@runtime_checkable` for the `MarketSource` interface, `String` + `CheckConstraint` (not native Postgres ENUM) for status to avoid ALTER TYPE locking issues, and a simple `bet_count` integer column on `markets` for the criteria-locking mechanism (incremented by Phase 5 bet placement, checked by Phase 4 edit endpoint).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Async protocol methods -- codebase uses `AsyncSession` everywhere; both HouseAdapter (DB) and future PolymarketAdapter (HTTP) are async by nature
- Adapter methods return ORM models -- adapters are internal; routers serialize to Pydantic. Avoids double-conversion and lets service layer use ORM relations
- Dict-based singleton registry: `REGISTRY: dict[MarketSourceEnum, MarketSource]` in `market_source.py` -- simple, discoverable, testable. Phase 6 adds `REGISTRY[POLYMARKET] = PolymarketAdapter()`
- `detect_resolution()` in HouseAdapter returns `None` always -- house markets resolve via explicit admin action (Phase 5), not auto-detection
- Full lifecycle status enum: DRAFT, OPEN, CLOSED, RESOLVED, CANCELLED -- Phase 4 uses OPEN/CLOSED, Phase 5 adds RESOLVED transitions
- Odds stored as Decimal probability 0-1 (`Numeric(8,6)`) -- Polymarket uses 0-1, math is natural
- Auto-generated slug from question via `python-slugify` + UUID suffix for uniqueness
- `odds_snapshots` table created in Phase 4 migration -- HouseAdapter writes snapshot on create/edit
- Offset-limit pagination (`?page=1&page_size=20`)
- Endpoint prefix: `/api/v1/admin/markets` for admin CRUD; `/api/v1/markets` for public read-only list
- Backend API only (no admin frontend in Phase 4)
- Public market list endpoint at `/api/v1/markets` -- no auth required, returns open markets with odds
- Migration naming: `0003_phase4_markets.py`
- Test organization: `backend/tests/markets/` directory
- Error handling: follow Phase 2 patterns (HTTPException with detail dict)
- Audit events: `market.created`, `market.updated`, `market.closed` following D-40 convention

### Claude's Discretion
- Migration naming: `0003_phase4_markets.py` (follows `0001_phase1_foundations`, `0002_phase2_auth` pattern)
- Test organization: `backend/tests/markets/` directory matching the `app/markets/` module pattern
- Error handling conventions: follow Phase 2 patterns (HTTPException with detail dict)
- Audit events: `market.created`, `market.updated`, `market.closed` following D-40 convention from Phase 1

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MKT-07 | Mirrored markets stored with Polymarket `condition_id` + `market_id` for reverse lookup | Schema design includes `source` + `source_market_id` columns; `condition_id` added as nullable Text for Phase 6 forward-compat |
| MKT-08 | v1 supports binary outcomes only (YES/NO); multi-outcome explicitly deferred to v2 | Binary-only CHECK constraint on outcomes table (count per market = 2); Architecture Patterns section details enforcement approach |
| ADM-01 | Admin can view paginated list of all markets across sources with filters (source, status, category) | Pagination pattern documented; filter query pattern with optional enum params |
| ADM-02 | Admin can create a house market with question, resolution criteria, deadline, initial odds (default 50/50), optional category | MarketCreate schema; HouseAdapter.create_market(); slug generation; OddsSnapshot write-on-create |
| ADM-03 | Admin can edit a house market's odds, deadline, and resolution criteria while zero bets | Criteria-locking mechanism via `bet_count` column; 423 Locked HTTP status |
| ADM-04 | Admin can close a house market early (stops accepting new bets) | Status transition OPEN -> CLOSED; closed market rejects bets at API level |
| ADM-07 | After first bet, resolution criteria locked (UI disabled + API rejects) | `bet_count` integer column pattern; CHECK in edit endpoint; 423 response |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Language: Spanish for conversation, English for code and paths
- Python "pelado" is broken on Windows -- use venv/uv
- `uv` for Python deps, `pnpm` for frontend
- All money columns use `Mapped[Money]` (Numeric(18,4)) -- odds use `Numeric(8,6)` which is NOT a money column (different purpose/precision)
- `tenant_id` ghost column on all player-owned and market tables
- Audit logging via `AuditService.record()` only -- never raw INSERT
- structlog only -- no print, no loguru
- Settings via `Settings()` only -- never `os.getenv`
- `from __future__ import annotations` is problematic with FastAPI's `inspect.signature` -- omit from router files (see Phase 2 admin_router.py deviation)

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| MarketSource Protocol definition | API / Backend | -- | Pure Python typing contract; no database or client involvement |
| HouseAdapter implementation | API / Backend | Database / Storage | Adapter wraps async DB queries; data lives in Postgres |
| Market/Outcome/OddsSnapshot models | Database / Storage | API / Backend | SQLAlchemy ORM models mapping to Postgres tables |
| Admin CRUD endpoints | API / Backend | -- | FastAPI routers with Bearer JWT auth |
| Public market list | API / Backend | -- | Read-only FastAPI endpoint, no auth |
| Slug generation | API / Backend | -- | Application-level via python-slugify |
| Criteria locking (after first bet) | API / Backend | Database / Storage | Application check on `bet_count` column; Phase 5 increments via DB |
| Pagination | API / Backend | -- | Offset-limit query params → SQLAlchemy `.offset()/.limit()` |
| Audit logging | API / Backend | Database / Storage | AuditService writes atomically in caller's session |

## Standard Stack

### Core (already installed)
| Library | Version | Purpose | Source |
|---------|---------|---------|--------|
| SQLAlchemy | 2.0.50 | ORM + async models | [VERIFIED: uv pip show in project venv] |
| asyncpg | >=0.30 | Async Postgres driver | [VERIFIED: pyproject.toml] |
| FastAPI | >=0.115.7 | HTTP framework + routers | [VERIFIED: pyproject.toml] |
| Pydantic | >=2.10 | Schema validation | [VERIFIED: pyproject.toml] |
| Alembic | >=1.14 | Database migrations | [VERIFIED: pyproject.toml] |

### New dependency
| Library | Version | Purpose | Source |
|---------|---------|---------|--------|
| python-slugify | 8.0.4 | Slug generation from market questions | [ASSUMED] -- PyPI page confirms 8.0.4 is latest (Feb 2024), MIT license, 66M downloads/month; but package name not verified via Context7 or official FastAPI/SQLAlchemy docs |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| python-slugify | Manual `re.sub` + `str.lower()` | python-slugify handles Unicode, transliteration, edge cases; manual regex is fragile for international characters in market questions |
| Postgres ENUM for status | String + CHECK constraint | ENUM requires `ALTER TYPE` with ACCESS EXCLUSIVE lock to add values; CHECK constraint is a simple `ALTER TABLE` -- see Architecture Patterns |
| Numeric(8,6) for odds | Numeric(18,4) (Money alias) | Odds are probability 0-1, not currency; 8,6 gives 6 decimal places (0.123456) which is more than enough precision for display; Money alias (18,4) would waste storage and conflate odds with money semantics |

**Installation:**
```bash
cd backend && uv add "python-slugify>=8.0,<9.0"
```

## Package Legitimacy Audit

> slopcheck was unavailable at research time. All packages are tagged `[ASSUMED]` and the planner must gate each install behind a `checkpoint:human-verify` task.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| python-slugify | PyPI | ~10 yrs | 66M/month | [github.com/un33k/python-slugify](https://github.com/un33k/python-slugify) | N/A | [ASSUMED] -- planner must verify |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*slopcheck was unavailable at research time. The single new package (`python-slugify`) is tagged `[ASSUMED]` and the planner must gate its install behind a `checkpoint:human-verify` task. Given its 10-year history and 66M monthly downloads, risk is minimal but protocol requires the gate.*

## Architecture Patterns

### System Architecture Diagram

```
Admin (Bearer JWT)                    Player (no auth)
       |                                    |
       v                                    v
POST/PUT/PATCH /api/v1/admin/markets   GET /api/v1/markets
       |                                    |
       v                                    v
  AdminMarketRouter ────────────── PublicMarketRouter
       |                                    |
       v                                    v
  MarketService (business logic, validation, audit)
       |
       v
  MarketSource Protocol ◄──── REGISTRY dict
       |                          |
       v                          v
  HouseAdapter ──────────── (Phase 6: PolymarketAdapter)
       |
       v
  AsyncSession ───► Postgres (markets, outcomes, odds_snapshots)
```

Data flow for market creation:
1. Admin POST with Bearer JWT -> FastAPI validates auth via `current_active_admin`
2. Router deserializes `MarketCreate` Pydantic schema
3. MarketService calls `HouseAdapter.create_market()` (or generic via registry)
4. HouseAdapter: INSERT market + 2 outcomes (YES/NO) + 1 odds_snapshot, within one transaction
5. AuditService.record() writes `market.created` in the same session
6. Router serializes ORM model to `MarketRead` Pydantic response

### Recommended Project Structure
```
backend/app/
├── markets/
│   ├── __init__.py          # Module init
│   ├── models.py            # Market, Outcome, OddsSnapshot ORM models
│   ├── schemas.py           # Pydantic schemas (MarketCreate, MarketRead, MarketUpdate, etc.)
│   ├── service.py           # MarketService (business logic, validation, criteria locking)
│   ├── router.py            # Admin + public routers
│   └── enums.py             # MarketStatus, MarketSource Python enums
├── integrations/
│   ├── __init__.py          # Updated stub
│   └── market_source.py     # MarketSource Protocol + REGISTRY + HouseAdapter
```

### Pattern 1: MarketSource Protocol + Registry

**What:** A `typing.Protocol` defining the interface all market source adapters must implement. A module-level dict maps `MarketSourceEnum` values to adapter instances.

**When to use:** Every market query or operation that must be source-agnostic.

```python
# Source: typing.Protocol official docs (https://docs.python.org/3/library/typing.html#typing.Protocol)
# + codebase pattern (app/auth/deps.py lazy exports)

from typing import Protocol, runtime_checkable
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

@runtime_checkable
class MarketSource(Protocol):
    """Source-agnostic market operations.

    Every adapter (HouseAdapter, PolymarketAdapter) implements this.
    Methods are async because both DB (HouseAdapter) and HTTP
    (PolymarketAdapter) are naturally async in this codebase.
    """

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

**Registry pattern:**
```python
from app.markets.enums import MarketSourceEnum

# Module-level singleton. Phase 4 registers HOUSE; Phase 6 adds POLYMARKET.
REGISTRY: dict[MarketSourceEnum, MarketSource] = {}

def register_source(source: MarketSourceEnum, adapter: MarketSource) -> None:
    REGISTRY[source] = adapter

def get_adapter(source: MarketSourceEnum) -> MarketSource:
    return REGISTRY[source]
```

### Pattern 2: Status as String + CHECK Constraint (not native ENUM)

**What:** Market status stored as `String(20)` with a `CheckConstraint` listing valid values, rather than Postgres native ENUM type.

**Why:** Native Postgres ENUM requires `ALTER TYPE ... ADD VALUE` which acquires an ACCESS EXCLUSIVE lock on the entire table -- blocking all reads and writes. For a status field that may gain values in Phase 5 (RESOLVED) and future phases, this is a migration hazard. `String + CHECK` only requires `ALTER TABLE ... DROP CONSTRAINT / ADD CONSTRAINT` which is much lighter. [CITED: https://www.crunchydata.com/blog/enums-vs-check-constraints-in-postgres]

**When to use:** All enum-like columns in this phase (market status, market source).

```python
# In models.py
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

class Market(Base):
    __tablename__ = "markets"
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

    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, server_default="OPEN",
    )
```

```python
# In enums.py -- Python-side enum for type safety in application code
import enum

class MarketStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    RESOLVED = "RESOLVED"
    CANCELLED = "CANCELLED"

class MarketSourceEnum(str, enum.Enum):
    HOUSE = "HOUSE"
    POLYMARKET = "POLYMARKET"
```

### Pattern 3: Criteria Locking via bet_count Column

**What:** A `bet_count` integer column on `markets` that starts at 0 and is incremented atomically by Phase 5's bet placement transaction. Phase 4's edit endpoint checks `market.bet_count == 0` before allowing criteria edits.

**Why this pattern over alternatives:**
- **Subquery `EXISTS (SELECT 1 FROM bets WHERE ...)`**: Requires the `bets` table to exist (Phase 5). Phase 4 cannot test this without stubbing.
- **Trigger on bets table**: Same dependency issue plus trigger complexity.
- **`bet_count` column**: Self-contained in Phase 4; Phase 5 atomically increments it in the bet placement transaction (`UPDATE markets SET bet_count = bet_count + 1 WHERE id = ?`). Testable in Phase 4 by directly setting `bet_count = 1` in fixtures.

```python
# In service.py edit flow
if market.bet_count > 0 and update_data.resolution_criteria is not None:
    raise HTTPException(
        status_code=423,  # Locked
        detail={"code": "CRITERIA_LOCKED", "reason": "Resolution criteria cannot be changed after bets have been placed"},
    )
```

### Pattern 4: Offset-Limit Pagination

**What:** Page-based pagination via query params `page` (1-indexed) and `page_size` (default 20, max 100). Returns total count for UI page navigation. [CITED: https://sqlmodel.tiangolo.com/tutorial/fastapi/limit-and-offset/]

```python
# In schemas.py
from pydantic import BaseModel, Field

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
    pages: int  # ceil(total / page_size)
```

```python
# In router.py -- FastAPI Depends pattern for pagination
from fastapi import Query

async def pagination_params(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginationParams:
    return PaginationParams(page=page, page_size=page_size)
```

### Pattern 5: Slug Generation

**What:** Auto-generate URL-friendly slug from market question + 4-char UUID suffix for uniqueness.

```python
# In service.py
from slugify import slugify
from uuid import uuid4

def generate_slug(question: str) -> str:
    """Generate URL slug from question with UUID suffix for uniqueness.

    Example: "Will Bitcoin hit $100k?" -> "will-bitcoin-hit-100k-a3f2"
    """
    base = slugify(question, max_length=80)
    suffix = uuid4().hex[:4]
    return f"{base}-{suffix}"
```

### Anti-Patterns to Avoid

- **Native Postgres ENUM for status:** Requires ACCESS EXCLUSIVE lock on ALTER TYPE. Use String + CHECK instead. [CITED: https://www.crunchydata.com/blog/enums-vs-check-constraints-in-postgres]
- **Lazy-loading relationships in async context:** SQLAlchemy 2.0 async does not support implicit lazy loading. Always use `selectinload()` or `joinedload()` in queries that need related objects. [CITED: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html]
- **Shared AsyncSession across coroutines:** A single `AsyncSession` is NOT safe for concurrent use. Each request gets its own session via the `get_async_session` FastAPI dependency. [CITED: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html]
- **`from __future__ import annotations` in router files:** Breaks FastAPI's `inspect.signature` dependency resolution. Omit from any file declaring `Annotated[T, Depends(...)]` (established deviation from Phase 2).
- **Money alias for odds columns:** Odds are probability 0-1, not currency. Use `Numeric(8,6)` directly, not the `Money` alias (which is `Numeric(18,4)`). The money-lint will NOT flag odds columns because `odds` and `probability` are not in the MONEY_NAMES list.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Slug generation | regex replace + lowering | `python-slugify` | Handles Unicode transliteration, max_length, separator customization; manual regex breaks on CJK, Arabic, accented chars |
| Pagination | Manual offset arithmetic | `PaginationParams` dependency + `PaginatedResponse` generic | Consistent interface across all paginated endpoints (Phase 4 markets, Phase 5 bets, Phase 8 users) |
| Status validation | Application-only string checking | Python `str` enum + DB `CHECK` constraint | Defense in depth: app enum catches at serialization, DB CHECK catches at insert/update |
| UUID primary keys | Custom ID generation | `uuid4()` + `func.gen_random_uuid()` server_default | Established codebase pattern (User, RefreshToken, AuditLog all use this) |
| Audit logging | Direct INSERT into audit_log | `AuditService.record()` | CONVENTIONS.md section 6: single allowed API; atomic with caller's session |

**Key insight:** Phase 4 introduces only ONE new dependency (python-slugify). Everything else -- ORM patterns, audit, auth deps, session management, pagination -- builds on Phase 1-2 foundations. The less novel code, the fewer bugs.

## Common Pitfalls

### Pitfall 1: Using native Postgres ENUM for market status
**What goes wrong:** Adding a new status value (e.g., RESOLVED in Phase 5) requires `ALTER TYPE market_status ADD VALUE 'RESOLVED'` which acquires an ACCESS EXCLUSIVE lock, blocking all reads and writes on every table using that type.
**Why it happens:** ENUM feels "cleaner" for fixed value sets; developers don't anticipate the ALTER TYPE pain until migration day.
**How to avoid:** Use `String(20) + CheckConstraint` as documented in Architecture Patterns section. All valid values defined in Phase 4 migration; Phase 5 just needs a `DROP CONSTRAINT / ADD CONSTRAINT` pair (much lighter).
**Warning signs:** Alembic autogenerate producing `sa.Enum(...)` types in migration files.

### Pitfall 2: Lazy loading relationships in async session
**What goes wrong:** Accessing `market.outcomes` after the query triggers an implicit SQL load that fails with `MissingGreenlet` in async context.
**Why it happens:** SQLAlchemy 2.0 async prohibits implicit IO (lazy loading). The default `relationship()` uses `lazy="select"` which is sync-only.
**How to avoid:** Always eagerly load relationships in the query: `select(Market).options(selectinload(Market.outcomes))`. Set `lazy="raise"` on relationships as a safety net to catch accidental lazy loads at development time.
**Warning signs:** `sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called` errors in tests.

### Pitfall 3: Odds precision mismatch between storage and display
**What goes wrong:** Storing odds as `Numeric(8,6)` (e.g., `0.523400`) but API returns it as a Python float (e.g., `0.5234`) losing trailing zeros, or JSON serialization introduces floating-point noise.
**Why it happens:** Pydantic v2 serializes `Decimal` as float by default in JSON.
**How to avoid:** In Pydantic response schemas, use `ConfigDict(json_encoders={Decimal: str})` or annotate odds fields with `Field(serialization_alias=...)` and a custom serializer that outputs string. Same principle as money columns but for odds.
**Warning signs:** API responses contain `0.5000000000000001` instead of `"0.50"`.

### Pitfall 4: Missing forward-compat columns for Phase 5 and 6
**What goes wrong:** Phase 5 needs `bet_count` on markets to implement criteria locking. Phase 6 needs `condition_id` for Polymarket reverse lookup. If Phase 4 migration doesn't include these, Phase 5/6 needs ALTER TABLE.
**Why it happens:** Tunnel vision on current phase scope.
**How to avoid:** Include `bet_count INTEGER NOT NULL DEFAULT 0` and `condition_id TEXT NULL` in the Phase 4 migration. Both are nullable or have defaults, so they don't affect Phase 4 logic but save Phase 5/6 a migration.
**Warning signs:** Phase 5 planning discovers it needs schema changes that should have been in Phase 4.

### Pitfall 5: Forgetting tenant_id ghost column on new tables
**What goes wrong:** New tables (markets, outcomes, odds_snapshots) ship without `tenant_id`, breaking the PLT-01 contract established in Phase 1.
**Why it happens:** Copy-paste from a model that doesn't have it, or simply forgetting.
**How to avoid:** Every new ORM model gets the tenant_id ghost column verbatim from CONVENTIONS.md section 2. The Alembic migration must include it with the same `TENANT_DEFAULT` constant.
**Warning signs:** grep for `tenant_id` returns fewer tables than expected; Phase 11 "Looks Done But Isn't" check fails.

### Pitfall 6: Not registering new models in alembic/env.py
**What goes wrong:** `alembic revision --autogenerate` doesn't see the new Market/Outcome/OddsSnapshot models because they aren't imported in `env.py`, producing an empty migration.
**Why it happens:** env.py requires explicit side-effect imports of every model module.
**How to avoid:** Add `from app.markets.models import Market, Outcome, OddsSnapshot  # noqa: F401` to `alembic/env.py` alongside existing model imports.
**Warning signs:** Generated migration has no `op.create_table` calls.

## Code Examples

### Market ORM Model (verified from codebase patterns)

```python
# Source: Codebase pattern from app/auth/models.py + app/core/audit/models.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID as PyUUID, uuid4

import sqlalchemy as sa
from sqlalchemy import DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.db.base import Base


class Market(Base):
    __tablename__ = "markets"
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

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid4, server_default=func.gen_random_uuid(),
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    resolution_criteria: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="HOUSE")
    source_market_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    condition_id: Mapped[str | None] = mapped_column(String(200), nullable=True)  # Phase 6 Polymarket
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="OPEN")
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bet_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
        default=lambda: get_settings().TENANT_ID_DEFAULT,
    )

    # Relationships -- use lazy="raise" to catch accidental lazy loads in async
    outcomes: Mapped[list[Outcome]] = relationship(
        back_populates="market", cascade="all, delete-orphan", lazy="raise",
    )
    odds_snapshots: Mapped[list[OddsSnapshot]] = relationship(
        back_populates="market", cascade="all, delete-orphan", lazy="raise",
    )
```

### Outcome ORM Model

```python
class Outcome(Base):
    __tablename__ = "outcomes"

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid4, server_default=func.gen_random_uuid(),
    )
    market_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("markets.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    label: Mapped[str] = mapped_column(String(50), nullable=False)  # "YES" or "NO"
    initial_odds: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    current_odds: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)

    tenant_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
        default=lambda: get_settings().TENANT_ID_DEFAULT,
    )

    market: Mapped[Market] = relationship(back_populates="outcomes")
```

### Admin Router Pattern

```python
# Source: Codebase pattern from app/auth/admin_router.py
# Note: NO `from __future__ import annotations` -- breaks FastAPI Depends

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_active_admin
from app.auth.models import User
from app.db.session import get_async_session

admin_market_router = APIRouter(
    prefix="/api/v1/admin/markets",
    tags=["admin-markets"],
    dependencies=[Depends(current_active_admin)],  # ALL routes require admin
)

@admin_market_router.post("", status_code=status.HTTP_201_CREATED)
async def create_market(
    request: Request,
    body: MarketCreate,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
) -> MarketRead:
    # ... service call + audit ...
    pass
```

### Alembic Migration Pattern

```python
# Source: Codebase pattern from 0001_phase1_foundations.py + 0002_phase2_auth.py
revision: str = "0003_phase4_markets"
down_revision: str | None = "0002_phase2_auth"

TENANT_DEFAULT = "00000000-0000-0000-0000-000000000001"

def upgrade() -> None:
    # markets table first (no FK deps)
    op.create_table("markets", ...)

    # outcomes table (FK to markets)
    op.create_table("outcomes", ...)

    # odds_snapshots table (FK to markets + outcomes)
    op.create_table("odds_snapshots", ...)

    # Binary-only constraint: trigger or application-level check
    # (see Architecture Patterns -- application-level is preferred)

def downgrade() -> None:
    # Drop in reverse FK order
    op.drop_table("odds_snapshots")
    op.drop_table("outcomes")
    op.drop_table("markets")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Postgres native ENUM | String + CHECK constraint | Industry trend ~2023+ | Avoids ALTER TYPE locking; easier migration evolution |
| ABC base class for adapters | `typing.Protocol` (PEP 544) | Python 3.8+ (2019) | Structural subtyping; no inheritance coupling; better for Plugin patterns |
| SQLAlchemy 1.x lazy loading | Explicit eager loading (selectinload) | SQLAlchemy 2.0 (2023) | Required for async; lazy="raise" catches mistakes |
| Float for probability | Decimal / Numeric(8,6) | Best practice always | Exact arithmetic; no floating-point noise in odds display |

**Deprecated/outdated:**
- `passlib` for password hashing: replaced by `pwdlib` in fastapi-users v14+ [CITED: STACK.md section 1.3]
- SQLAlchemy `declarative_base()` function: replaced by `DeclarativeBase` class in 2.0 [CITED: codebase uses `class Base(DeclarativeBase)` already]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `python-slugify` 8.0.4 is the correct package name on PyPI (not the confusable `slugify` or `awesome-slugify`) | Standard Stack | Wrong package would fail import or introduce malicious dependency; mitigated by `from slugify import slugify` import path which is unique to python-slugify |
| A2 | `Numeric(8,6)` is sufficient precision for odds (6 decimal places, max value 99.999999) | Architecture Patterns | If Polymarket sends odds with >6 decimal precision, truncation would occur; mitigated by Polymarket using 2-decimal prices (0.XX) in practice |
| A3 | `lazy="raise"` on SQLAlchemy relationships works correctly in 2.0.50 async context | Code Examples | If "raise" strategy isn't supported, lazy loads would silently fail or error differently; verified behavior exists in SQLAlchemy 2.0 docs |

## Open Questions

1. **Binary-only enforcement at DB level vs application level**
   - What we know: CONTEXT says "deferrable CHECK constraint or trigger" for binary-only (2 outcomes per market). Application-level is simpler and testable.
   - What's unclear: Whether a DB-level trigger counting outcomes per market is worth the complexity, given v2 will relax this to multi-outcome.
   - Recommendation: Application-level enforcement in `MarketService.create_market()` (always creates exactly 2 outcomes for binary markets) PLUS a simple CHECK or trigger that prevents >2 outcomes per market as defense-in-depth. Keep the trigger simple and mark it as v2-removable.

2. **OddsSnapshot table FK structure**
   - What we know: Needs market_id and outcome_id FKs, plus the probability value and timestamp.
   - What's unclear: Whether to store one row per outcome per snapshot (2 rows for binary: YES=0.55, NO=0.45) or one row per market with both odds in JSONB.
   - Recommendation: One row per outcome per snapshot (normalized). Cleaner for queries, works naturally with multi-outcome in v2, and the price-history chart in Phase 9 queries by outcome_id.

3. **Phase 3 dependency: does Phase 4 need the wallet/ledger tables to exist?**
   - What we know: Phase 4 depends on Phase 1 (scaffold + tenant_id) and Phase 2 (admin role for CRUD). ROADMAP says Phase 3 (wallet) is not a prerequisite.
   - What's unclear: Whether Phase 4 migration (0003) can skip 0002.5 if Phase 3 hasn't shipped yet.
   - Recommendation: Phase 4 migration revision chain is `0002_phase2_auth -> 0003_phase4_markets`. If Phase 3 ships first (as ROADMAP implies), its migration would be between 0002 and 0003. If Phase 4 ships before Phase 3 (parallel work), Phase 3 migration needs to be 0004 or the chain needs rebasing. **The ROADMAP implies sequential order (3 before 4), so this is likely moot.**

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12+ | Backend runtime | Yes | 3.13.7 (via uv) | -- |
| SQLAlchemy | ORM models | Yes | 2.0.50 | -- |
| asyncpg | Postgres driver | Yes | >=0.30 | -- |
| FastAPI | HTTP framework | Yes | >=0.115.7 | -- |
| Alembic | Migrations | Yes | >=1.14 | -- |
| Postgres 16 | Database | Yes (Docker) | 16-alpine | -- |
| python-slugify | Slug generation | No (not installed yet) | 8.0.4 target | Manual regex (degraded) |

**Missing dependencies with no fallback:** None
**Missing dependencies with fallback:** python-slugify -- `uv add` during Phase 4 execution

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3+ / pytest-asyncio 0.24+ |
| Config file | `backend/pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `cd backend && uv run pytest tests/markets/ -x -q` |
| Full suite command | `cd backend && uv run pytest -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MKT-07 | Markets have source + source_market_id columns | integration | `uv run pytest tests/markets/test_models.py::test_market_source_columns -x` | Wave 0 |
| MKT-08 | Binary-only (2 outcomes per market) | integration | `uv run pytest tests/markets/test_models.py::test_binary_only_constraint -x` | Wave 0 |
| ADM-01 | Admin market list paginated with filters | integration | `uv run pytest tests/markets/test_admin_router.py::test_list_markets_paginated -x` | Wave 0 |
| ADM-02 | Admin create binary house market | integration | `uv run pytest tests/markets/test_admin_router.py::test_create_house_market -x` | Wave 0 |
| ADM-03 | Admin edit while zero bets; locked after bet | integration | `uv run pytest tests/markets/test_admin_router.py::test_edit_market_zero_bets -x` | Wave 0 |
| ADM-03+07 | 423 Locked when criteria edit after first bet | integration | `uv run pytest tests/markets/test_admin_router.py::test_criteria_locked_after_bet -x` | Wave 0 |
| ADM-04 | Admin close market early | integration | `uv run pytest tests/markets/test_admin_router.py::test_close_market -x` | Wave 0 |
| ADM-04 | Bet rejected on closed market | integration | `uv run pytest tests/markets/test_admin_router.py::test_bet_rejected_closed_market -x` | Wave 0 |
| Protocol | HouseAdapter implements MarketSource | unit | `uv run pytest tests/markets/test_protocol.py::test_house_adapter_protocol -x` | Wave 0 |
| Protocol | Registry returns correct adapter | unit | `uv run pytest tests/markets/test_protocol.py::test_registry_lookup -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && uv run pytest tests/markets/ -x -q`
- **Per wave merge:** `cd backend && uv run pytest -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/markets/__init__.py` -- module init
- [ ] `backend/tests/markets/conftest.py` -- market fixtures (admin_user, sample market, session overrides)
- [ ] `backend/tests/markets/test_models.py` -- ORM model tests (columns, constraints, relationships)
- [ ] `backend/tests/markets/test_admin_router.py` -- admin endpoint integration tests
- [ ] `backend/tests/markets/test_public_router.py` -- public endpoint tests
- [ ] `backend/tests/markets/test_protocol.py` -- Protocol conformance + registry tests
- [ ] `backend/tests/markets/test_service.py` -- MarketService business logic tests
- [ ] `backend/tests/markets/test_migration_0003.py` -- migration schema verification

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (admin endpoints) | Bearer JWT via `current_active_admin` dependency (Phase 2) |
| V3 Session Management | no (no new session logic) | Inherited from Phase 2 |
| V4 Access Control | yes | Admin-only routes via `Depends(current_active_admin)`; public routes have no write capability |
| V5 Input Validation | yes | Pydantic v2 schemas (MarketCreate, MarketUpdate); query param validation via FastAPI `Query()` |
| V6 Cryptography | no | No new crypto in this phase |

### Known Threat Patterns for this Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Admin endpoint access without auth | Elevation of Privilege | `Depends(current_active_admin)` on all `/api/v1/admin/*` routes; negative test confirming 401/403 |
| SQL injection via filter params | Tampering | SQLAlchemy parameterized queries (never raw string interpolation); Pydantic enum validation on filter values |
| Mass assignment on market update | Tampering | Explicit `MarketUpdate` Pydantic schema listing only editable fields; criteria-lock check before any update |
| Market data enumeration by non-admin | Information Disclosure | Public endpoint returns only OPEN markets; admin endpoints require Bearer JWT |
| Slug collision leading to wrong market | Spoofing | UUID suffix on slugs + UNIQUE constraint on slug column |

## Sources

### Primary (HIGH confidence)
- Codebase files: `app/auth/models.py`, `app/auth/admin_router.py`, `app/core/audit/service.py`, `app/db/types.py`, `app/db/session.py`, `app/main.py`, `alembic/versions/0001_phase1_foundations.py`, `alembic/versions/0002_phase2_auth.py`, `backend/CONVENTIONS.md` -- all read and verified for pattern extraction
- [SQLAlchemy 2.0 Async Documentation](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) -- async session patterns, lazy loading gotchas, relationship handling
- [Crunchy Data: Enums vs CHECK Constraints](https://www.crunchydata.com/blog/enums-vs-check-constraints-in-postgres) -- ENUM vs CHECK analysis

### Secondary (MEDIUM confidence)
- [python-slugify PyPI page](https://pypi.org/project/python-slugify/) -- version 8.0.4 confirmed, 66M downloads/month
- [SQLModel pagination tutorial](https://sqlmodel.tiangolo.com/tutorial/fastapi/limit-and-offset/) -- offset-limit pattern for FastAPI
- [Python typing.Protocol docs](https://docs.python.org/3/library/typing.html#typing.Protocol) -- Protocol + runtime_checkable usage
- [PEP 544](https://peps.python.org/pep-0544/) -- Structural subtyping specification

### Tertiary (LOW confidence)
- None -- all claims verified against primary or secondary sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed except python-slugify (well-known, 10yr history)
- Architecture: HIGH -- patterns directly derived from existing codebase (auth models, router, audit)
- Pitfalls: HIGH -- Postgres ENUM vs CHECK verified against Crunchy Data; async lazy loading verified against SQLAlchemy docs; criteria locking is a novel pattern but simple
- Forward compatibility: MEDIUM -- Phase 5/6 column needs (bet_count, condition_id) inferred from ROADMAP requirements, not yet validated against Phase 5/6 research

**Research date:** 2026-05-27
**Valid until:** 2026-06-27 (stable domain; no fast-moving dependencies)
