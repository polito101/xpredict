# Phase 8: Admin CRM (User Management & Audit Log Viewer) - Pattern Map

**Mapped:** 2026-05-28
**Files analyzed:** 26 new/modified files
**Analogs found:** 22 / 26

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/app/admin/router.py` | controller | request-response | `backend/app/markets/router.py` | exact |
| `backend/app/admin/schemas.py` | model | transform | `backend/app/markets/schemas.py` | exact |
| `backend/app/admin/service.py` | service | CRUD | `backend/app/markets/service.py` | exact |
| `backend/app/admin/csv_export.py` | utility | transform | (no analog -- new pattern) | none |
| `backend/app/core/audit/router.py` | controller | request-response | `backend/app/markets/router.py` | role-match |
| `backend/app/main.py` (modify) | config | request-response | (self -- add include_router) | self |
| `backend/app/auth/manager.py` (modify) | middleware | request-response | `backend/app/bets/router.py` lines 49-63 | role-match |
| `backend/app/wallet/admin_router.py` (modify) | controller | request-response | (self -- add banned check) | self |
| `backend/tests/admin/__init__.py` | test | -- | `backend/tests/markets/__init__.py` | exact |
| `backend/tests/admin/conftest.py` | test | -- | `backend/tests/markets/conftest.py` | exact |
| `backend/tests/admin/test_user_list.py` | test | integration | `backend/tests/markets/test_admin_router.py` | exact |
| `backend/tests/admin/test_user_detail.py` | test | integration | `backend/tests/markets/test_admin_router.py` | role-match |
| `backend/tests/admin/test_ban_unban.py` | test | integration | `backend/tests/markets/test_admin_router.py` | role-match |
| `backend/tests/admin/test_csv_export.py` | test | integration | `backend/tests/markets/test_admin_router.py` | role-match |
| `backend/tests/admin/test_audit_log.py` | test | integration | `backend/tests/markets/test_admin_router.py` | role-match |
| `backend/tests/admin/test_auth_negative.py` | test | integration | `backend/tests/markets/test_admin_router.py` lines 115-140 | exact |
| `frontend/src/app/admin/layout.tsx` (modify) | component | -- | (self -- replace placeholders with real links) | self |
| `frontend/src/app/admin/users/page.tsx` | component | request-response | `frontend/src/app/admin/page.tsx` | role-match |
| `frontend/src/app/admin/users/[id]/page.tsx` | component | request-response | `frontend/src/app/admin/page.tsx` | role-match |
| `frontend/src/app/admin/audit-log/page.tsx` | component | request-response | `frontend/src/app/admin/page.tsx` | role-match |
| `frontend/src/components/admin/*.tsx` (12 files) | component | event-driven | `frontend/src/app/admin/login/admin-login-form.tsx` | role-match |
| `frontend/src/lib/admin-api.ts` | utility | request-response | `frontend/src/lib/api.ts` + `frontend/src/lib/auth.ts` | exact |

## Pattern Assignments

### `backend/app/admin/router.py` (controller, request-response)

**Analog:** `backend/app/markets/router.py`

**Imports pattern** (lines 1-20):
```python
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_active_admin
from app.auth.models import User
from app.db.session import get_async_session
```

**Router instantiation pattern** (lines 26-29):
```python
admin_market_router = APIRouter(
    prefix="/api/v1/admin/markets",
    tags=["admin-markets"],
)
```
Phase 8 should use: `prefix="/api/v1/admin"`, `tags=["admin-crm"]`.

**Admin auth + session dependencies pattern** (lines 33-38 -- every endpoint):
```python
async def create_market(
    request: Request,
    body: MarketCreate,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
) -> MarketRead:
```

**Paginated list endpoint pattern** (lines 46-71):
```python
@admin_market_router.get("", response_model=PaginatedResponse[MarketListItem])
async def list_markets_admin(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    source: MarketSourceEnum | None = Query(default=None),
    status: MarketStatus | None = Query(default=None),
    category: str | None = Query(default=None),
) -> PaginatedResponse[MarketListItem]:
    source_val = source.value if source else None
    status_val = status.value if status else None
    items, total = await MarketService.list_markets(
        session,
        page=page,
        page_size=page_size,
        source=source_val,
        status=status_val,
        category=category,
    )
    return paginated_response(
        [MarketListItem.model_validate(m) for m in items],
        total,
        page,
        page_size,
    )
```

**Single-entity GET pattern** (lines 74-83):
```python
@admin_market_router.get("/{market_id}", response_model=MarketRead)
async def get_market_admin(
    market_id: UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
) -> MarketRead:
    market = await MarketService.get_market_by_id(session, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    return MarketRead.model_validate(market)
```

**State-change POST pattern** (lines 104-118 -- `close_market`):
```python
@admin_market_router.post("/{market_id}/close", response_model=MarketRead)
async def close_market(
    market_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
) -> MarketRead:
    market = await MarketService.get_market_by_id(session, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    ip = request.client.host if request.client else None
    closed = await MarketService.close_market(session, market, admin, ip=ip)
    await session.commit()
    refreshed = await MarketService.get_market_by_id(session, closed.id)
    return MarketRead.model_validate(refreshed)
```

**CRITICAL: No `from __future__ import annotations`** -- router files must NOT use it (Python 3.13 + FastAPI constraint). The markets router does not use it. Phase 8 router must follow this.

---

### `backend/app/admin/schemas.py` (model, transform)

**Analog:** `backend/app/markets/schemas.py`

**PaginatedResponse generic + paginated_response helper** (lines 21-36, 154-166):
```python
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

# ...

def paginated_response(
    items: list[T],
    total: int,
    page: int,
    page_size: int,
) -> PaginatedResponse[T]:
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, math.ceil(total / page_size)),
    )
```
Phase 8 should IMPORT `PaginatedResponse` and `paginated_response` from `app.markets.schemas` (not duplicate). New schemas are `UserListItem`, `UserDetail`, `BanRequest`, `AuditLogItem`, etc.

**Read schema with ConfigDict(from_attributes=True)** (lines 87-112):
```python
class MarketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    question: str
    slug: str
    # ...
    created_at: datetime
    updated_at: datetime
```

**Decimal-as-string serialization pattern** (lines 81-84, also `backend/app/wallet/schemas.py` lines 36-39):
```python
# From markets/schemas.py
@field_serializer("initial_odds", "current_odds")
@classmethod
def serialize_decimal(cls, v: Decimal) -> str:
    return str(v)

# From wallet/schemas.py -- the MoneyStr alias
MoneyStr = Annotated[
    Decimal,
    PlainSerializer(lambda v: str(v), return_type=str, when_used="json"),
]
```
Phase 8 should import `MoneyStr` from `app.wallet.schemas` for balance fields.

**Write schema with extra="forbid"** (`backend/app/wallet/schemas.py` lines 42-55):
```python
class RechargeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(gt=0, description="Amount to credit (positive Decimal).")
    reason: str = Field(min_length=1, description="Audit reason for the recharge.")
```
Phase 8 `BanRequest` should follow this pattern (extra="forbid", reason field with min_length=1).

---

### `backend/app/admin/service.py` (service, CRUD)

**Analog:** `backend/app/markets/service.py`

**Static service class pattern** (lines 18-20):
```python
class MarketService:
    @staticmethod
    async def create_market(
        session: AsyncSession,
        admin_user: User,
        body: MarketCreate,
        ip: str | None = None,
    ) -> Market:
```

**Paginated list query with filters + count** (lines 218-245):
```python
@staticmethod
async def list_markets(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    source: str | None = None,
    status: str | None = None,
    category: str | None = None,
) -> tuple[list[Market], int]:
    base = select(Market)
    if source:
        base = base.where(Market.source == source)
    if status:
        base = base.where(Market.status == status)
    if category:
        base = base.where(Market.category == category)

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    items_stmt = (
        base.options(selectinload(Market.outcomes))
        .order_by(Market.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await session.execute(items_stmt)
    return list(result.scalars().all()), total
```

**AuditService.record() call pattern** (lines 76-87):
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
Phase 8 ban/unban will use: `event_type="admin.user_banned"`, `payload={"target_user_id": str(user_id), "reason": reason}`.

**State-change with status validation** (lines 159-183):
```python
@staticmethod
async def close_market(
    session: AsyncSession,
    market: Market,
    admin_user: User,
    ip: str | None = None,
) -> Market:
    if market.status != MarketStatus.OPEN.value:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "INVALID_STATUS",
                "reason": f"Cannot close market with status {market.status}",
            },
        )
    market.status = MarketStatus.CLOSED.value
    market.closed_at = datetime.now(UTC)

    await AuditService.record(...)
    await session.flush()
    return market
```
Phase 8 ban/unban: check `banned_at IS NOT NULL` -> 409 "User is already banned"; set `banned_at = datetime.now(UTC)`.

---

### `backend/app/core/audit/router.py` (controller, request-response)

**Analog:** `backend/app/markets/router.py` (admin GET list pattern)

Same imports and `current_active_admin` dependency as `admin/router.py` above. The audit log router is a read-only endpoint with filter query params. Copy the paginated GET pattern from markets router lines 46-71, adding `event_type`, `actor`, `date_from`, `date_to` filters instead of `source`/`status`/`category`.

**AuditLog model reference** (`backend/app/core/audit/models.py` lines 23-52):
```python
class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, ...)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), ...)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    tenant_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, ...)
```

---

### `backend/app/wallet/admin_router.py` (modify -- add ban check)

**Analog for ban check pattern:** `backend/app/bets/router.py` lines 49-63

**Existing banned-user dependency pattern** (`bets/router.py`):
```python
async def current_betting_player(
    player: Annotated[User, Depends(current_active_player)],
) -> User:
    if player.banned_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is banned from placing bets.",
        )
    return player
```
Phase 8 adds a similar check in `recharge_wallet` (either inline or via a dependency). The recharge endpoint must check `banned_at` on the TARGET user (not the admin), so it is an inline check after loading the target user, not a dependency.

**MissingGreenlet prevention pattern** (`wallet/admin_router.py` lines 74-76):
```python
# Capture the admin id as a plain value NOW.
admin_id = admin.id
```
Phase 8 ban/unban service must capture `user.email`, `user.id` BEFORE `session.commit()` to avoid `MissingGreenlet`.

---

### `backend/app/main.py` (modify -- include router)

**Pattern** (lines 139-148):
```python
from app.markets.router import admin_market_router, public_market_router  # noqa: E402

app.include_router(health.router)
app.include_router(build_auth_routers())
app.include_router(admin_market_router)
# ...
```
Phase 8 adds:
```python
from app.admin.router import admin_crm_router  # noqa: E402
from app.core.audit.router import audit_admin_router  # noqa: E402

app.include_router(admin_crm_router)
app.include_router(audit_admin_router)
```

---

### `backend/tests/admin/conftest.py` (test fixtures)

**Analog:** `backend/tests/markets/conftest.py`

**Admin user fixture** (lines 32-51):
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
Phase 8 conftest needs: `admin_user`, `player_user` (non-admin), `banned_user` (player with `banned_at` set).

**Rate limiter reset autouse** (lines 19-28):
```python
@pytest.fixture(autouse=True)
def _reset_rate_limit_storage():
    from app.auth.rate_limit import limiter
    try:
        limiter._limiter.reset()
    except Exception:
        with contextlib.suppress(Exception):
            limiter._storage.reset()
    yield
```

---

### `backend/tests/admin/test_*.py` (integration tests)

**Analog:** `backend/tests/markets/test_admin_router.py`

**Test file header** (lines 1-14):
```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pwdlib import PasswordHash
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]
```

**Test helpers: seed user, get admin token, auth header** (lines 16-63):
```python
_ADMIN_EMAIL = "market-admin-router@test.com"
_ADMIN_PASSWORD = "Admin-Test-Pass-1!"

async def _client() -> httpx.AsyncClient:
    from app.main import app
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")

async def _seed_user(
    engine: AsyncEngine, email: str, *, is_superuser: bool = False,
) -> None:
    hashed = PasswordHash.recommended().hash(_ADMIN_PASSWORD)
    async with engine.connect() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :em"), {"em": email})
        await conn.execute(
            text(
                "INSERT INTO users "
                "(email, hashed_password, is_active, is_superuser, "
                " is_verified, display_name, token_version) "
                "VALUES (:em, :pw, TRUE, :su, TRUE, 'Test', 0)"
            ),
            {"em": email, "pw": hashed, "su": is_superuser},
        )
        await conn.commit()

async def _cleanup_user(engine: AsyncEngine, email: str) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :em"), {"em": email})
        await conn.commit()

async def _get_admin_token(client: httpx.AsyncClient) -> str:
    resp = await client.post(
        "/admin/auth/login",
        data={"username": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD},
    )
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["access_token"]

def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
```

**Test body pattern -- seed, act, assert, cleanup** (lines 77-96):
```python
async def test_create_market(engine: AsyncEngine) -> None:
    await _seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await _client() as c:
            token = await _get_admin_token(c)
            resp = await c.post(
                "/api/v1/admin/markets",
                json=_market_body(),
                headers=_auth(token),
            )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["question"] == "Will it rain tomorrow?"
    finally:
        await _cleanup_user(engine, _ADMIN_EMAIL)
```

**Negative auth test pattern** (lines 115-140):
```python
async def test_create_market_no_auth_returns_401(engine: AsyncEngine) -> None:
    async with await _client() as c:
        resp = await c.post("/api/v1/admin/markets", json=_market_body())
    assert resp.status_code == 401

async def test_create_market_non_admin_returns_403(engine: AsyncEngine) -> None:
    await _seed_user(engine, _PLAYER_EMAIL, is_superuser=False)
    try:
        async with await _client() as c:
            resp = await c.post(
                "/admin/auth/login",
                data={"username": _PLAYER_EMAIL, "password": _ADMIN_PASSWORD},
            )
            if resp.status_code == 200:
                token = resp.json()["access_token"]
                resp2 = await c.post(
                    "/api/v1/admin/markets",
                    json=_market_body(),
                    headers=_auth(token),
                )
                assert resp2.status_code == 403
            else:
                assert resp.status_code in (400, 401)
    finally:
        await _cleanup_user(engine, _PLAYER_EMAIL)
```

---

### `frontend/src/app/admin/users/page.tsx` (component, request-response)

**Analog:** `frontend/src/app/admin/page.tsx` (page structure) + `frontend/src/app/admin/login/admin-login-form.tsx` (client component)

**Admin page structure** (`admin/page.tsx` lines 14-24):
```typescript
export default function AdminHomePage() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <h1 className="text-3xl font-semibold tracking-tight">Admin dashboard</h1>
      <p className="mt-4 text-zinc-600 dark:text-zinc-400">
        ...
      </p>
    </div>
  );
}
```

**Client component "use client" + shadcn imports pattern** (`admin-login-form.tsx` lines 15-33):
```typescript
"use client";

import { useActionState, startTransition } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { z } from "zod";

import { adminLoginAction } from "@/lib/auth";
import { AdminLoginSchema, type ActionState } from "@/lib/auth-schemas";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
```
Phase 8 data tables will use `"use client"` + `@tanstack/react-table` + shadcn Table components.

---

### `frontend/src/lib/admin-api.ts` (utility, request-response)

**Analog:** `frontend/src/lib/api.ts` (types + fetch helpers) + `frontend/src/lib/auth.ts` (Server Action + cookie forwarding)

**Public API fetch pattern** (`api.ts` lines 35-52):
```typescript
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchMarkets(): Promise<MarketItem[]> {
  const res = await fetch(`${API_BASE}/api/v1/markets`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch markets: ${res.status}`);
  }
  return res.json() as Promise<MarketItem[]>;
}
```

**Admin Bearer cookie read + forward pattern** (`auth.ts` lines 307-364):
```typescript
"use server";

import { cookies } from "next/headers";

// Read admin_jwt cookie and forward as Bearer to FastAPI
const store = await cookies();
store.set("admin_jwt", access_token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/admin",
    maxAge: 900,
});
```
Phase 8 needs a Server Action or Route Handler that reads `admin_jwt` from cookies and forwards as `Authorization: Bearer` to FastAPI. Pattern:
```typescript
"use server";
import { cookies } from "next/headers";

async function adminApiFetch(path: string, init?: RequestInit) {
  const store = await cookies();
  const token = store.get("admin_jwt")?.value;
  if (!token) throw new Error("Not authenticated");
  const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";
  const res = await fetch(`${backendUrl}${path}`, {
    ...init,
    headers: { ...init?.headers, Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}
```

---

### `frontend/src/app/admin/layout.tsx` (modify -- activate nav links)

**Current placeholder** (lines 36-39):
```typescript
{/* Phase 8 will replace these placeholders with real CRM links. */}
<span className="text-zinc-400">Users</span>
<span className="text-zinc-400">Markets</span>
<span className="text-zinc-400">Audit log</span>
```
Phase 8 replaces with:
```typescript
<Link href="/admin/users" className="...">Users</Link>
<span className="text-zinc-400">Markets</span>
<Link href="/admin/audit-log" className="...">Audit log</Link>
```

---

## Shared Patterns

### Authentication (Admin Bearer)
**Source:** `backend/app/auth/deps.py` (lines 82-86 lazy re-export) + `backend/app/markets/router.py` (every endpoint)
**Apply to:** ALL new backend endpoints (`admin/router.py`, `core/audit/router.py`, CSV export)
```python
from app.auth.deps import current_active_admin
from app.auth.models import User

# Every endpoint signature:
admin: Annotated[User, Depends(current_active_admin)],
```

### Error Handling
**Source:** `backend/app/markets/router.py` lines 80-82, `backend/app/wallet/admin_router.py` lines 107-124
**Apply to:** All controller files
```python
# 404 pattern
if not entity:
    raise HTTPException(status_code=404, detail="Entity not found")

# Domain error mapping
except NoResultFound as exc:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="...") from exc
except InsufficientBalance as exc:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
```

### Pagination
**Source:** `backend/app/markets/schemas.py` lines 30-36, 154-166
**Apply to:** All list endpoints (user list, audit log, user transactions, user bets)
```python
from app.markets.schemas import PaginatedResponse, paginated_response

# In endpoint:
return paginated_response(items, total, page, page_size)
```

### Money Serialization
**Source:** `backend/app/wallet/schemas.py` lines 36-39
**Apply to:** All schemas with Decimal balance/amount fields
```python
from app.wallet.schemas import MoneyStr

class UserListItem(BaseModel):
    balance: MoneyStr  # Serialized as string in JSON
```

### AuditService.record()
**Source:** `backend/app/core/audit/service.py` lines 27-58
**Apply to:** Ban/unban endpoints
```python
from app.core.audit.service import AuditService

await AuditService.record(
    session,
    actor=f"user:{admin_id}",
    event_type="admin.user_banned",
    payload={"target_user_id": str(user_id), "reason": reason},
    ip=ip,
)
await session.commit()
```

### MissingGreenlet Prevention
**Source:** `backend/app/wallet/admin_router.py` lines 74-76
**Apply to:** Ban/unban service -- capture plain values BEFORE commit
```python
# Capture plain values before commit to avoid MissingGreenlet
admin_id = admin.id
user_id = user.id
user_email = user.email
```

### Ban Enforcement Check
**Source:** `backend/app/bets/router.py` lines 49-63
**Apply to:** Login check (auth manager), recharge check (wallet admin router)
```python
if user.banned_at is not None:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Account suspended",
    )
```

### Test Structure
**Source:** `backend/tests/markets/test_admin_router.py` lines 1-63
**Apply to:** ALL test files in `backend/tests/admin/`
```python
pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]

# Reusable helpers: _client(), _seed_user(), _cleanup_user(), _get_admin_token(), _auth()
```

### Frontend Admin Page Layout
**Source:** `frontend/src/app/admin/page.tsx` lines 14-24
**Apply to:** All new admin pages (users list, user detail, audit log)
```typescript
export default function AdminPage() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <h1 className="text-3xl font-semibold tracking-tight">Page Title</h1>
      {/* Content */}
    </div>
  );
}
```

### Frontend Client Component Pattern
**Source:** `frontend/src/app/admin/login/admin-login-form.tsx` lines 15-17
**Apply to:** All interactive admin components (data tables, forms, dialogs)
```typescript
"use client";

import { useState } from "react";
// shadcn + tanstack imports
```

## No Analog Found

Files with no close match in the codebase (planner should use RESEARCH.md patterns instead):

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `backend/app/admin/csv_export.py` | utility | transform | No CSV export exists in the codebase. Use Python stdlib `csv.DictWriter` + `io.StringIO` per RESEARCH.md Pattern 3. |
| `frontend/src/components/admin/users-data-table.tsx` | component | event-driven | No TanStack Table usage in codebase yet. Use RESEARCH.md Pattern 2 (TanStack Table v8 `useReactTable` with `manualPagination`/`manualSorting`). |
| `frontend/src/components/admin/audit-payload-viewer.tsx` | component | event-driven | No JSONB viewer component exists. Collapsible JSON block is a new pattern (D-12). |

## Metadata

**Analog search scope:** `backend/app/`, `backend/tests/`, `frontend/src/`
**Files scanned:** 48 existing files matched by glob; 15 read for pattern extraction
**Pattern extraction date:** 2026-05-28
