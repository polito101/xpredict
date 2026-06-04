# Phase 10: Admin KPI Dashboard & Configurable Branding - Pattern Map

**Mapped:** 2026-05-31
**Files analyzed:** 24 (new + modified, backend + frontend + tests)
**Analogs found:** 24 / 24 (every file has a concrete in-repo analog — this is a pure pattern-mirroring phase, zero new deps)

> All analogs below were READ this session and verified against the real merged codebase. The RESEARCH.md "Patterns to mirror" list is confirmed accurate; this map expands it into a per-file assignment with exact line ranges. Honor the project invariants flagged in `## Shared Patterns` (no `from __future__` in routers, `tenant_id` ghost, money-as-string, `extra="forbid"`, single Alembic head).

---

## File Classification

### Backend — NEW

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `backend/app/branding/models.py` (`TenantConfig`) | model | CRUD | `backend/app/markets/models.py` (`Market` class — String enum CHECK, `tenant_id` ghost, timestamps) | role-match (single-row table is new, but column/ghost/timestamp shape is identical) |
| `backend/alembic/versions/0009_phase10_tenant_config.py` | migration | DDL + singleton seed | `backend/alembic/versions/0004_phase3_wallet_ledger.py` (table + `ON CONFLICT DO NOTHING` singleton seed) **+** `0008_phase8_user_created_at.py` (single-head revision header shape) | exact (combine the two: header shape from 0008, seed pattern from 0004) |
| `backend/app/branding/schemas.py` (`TenantConfigRead`/`TenantConfigUpdate`/`BrandingPublic`) | schema | request-response | `backend/app/admin/schemas.py` (`extra="forbid"`, `from_attributes=True`, reuse `MoneyStr` import) **+** `backend/app/markets/schemas.py` `MarketCreate` (`Field(pattern=...)` validator) | exact |
| `backend/app/branding/admin_router.py` (`GET`/`PUT /api/v1/admin/tenant-config`) | router | CRUD | `backend/app/wallet/admin_router.py` (admin Bearer + body schema + audit write + MissingGreenlet `admin.id` capture) **+** `backend/app/admin/router.py` (GET/PUT shape, commit-then-return) | exact |
| `backend/app/branding/router.py` (public `GET /branding/current` + `GET /branding/logo`) | router | request-response | `backend/app/markets/router.py` `public_market_router` (public, no auth dep) + `Response(content=bytes, media_type=...)` for the logo bytes leg | role-match (public read + a raw-bytes Response leg is new shape) |
| `backend/app/admin/kpi_service.py` (or `app/admin/service.py` extension) | service | CRUD / aggregate (read-only) | `backend/app/wallet/service.py` `get_transactions` (lines 436-488 — `entries`→`transfers` join, `func.count().select_from()`) **+** `backend/app/core/audit/router.py` (lines 70-71 — `select(func.count()).select_from(subq)` for the DAU UNION) | exact for P&L join; role-match for DAU UNION |
| `backend/app/admin/kpi_schemas.py` (or extend `app/admin/schemas.py`) | schema | request-response | `backend/app/admin/schemas.py` (`MoneyStr` fields) + `backend/app/markets/schemas.py` `PriceHistoryResponse`/`PricePoint` (chart-bucket list shape) | exact |
| `backend/app/admin/kpi_router.py` (`GET /api/v1/admin/dashboard/kpis?window=`) | router | request-response | `backend/app/core/audit/router.py` (admin Bearer GET + `Query` param with `pattern=`) **+** `backend/app/admin/router.py` (admin prefix) | exact |
| 30-day synthetic bet seed/fixture | test fixture / seed | batch insert | `backend/tests/admin/_helpers.py` (raw-SQL committed seed: `seed_user` + wallet/bet INSERTs) | role-match |

### Backend — MODIFY

| Modified File | Change | Analog for the change |
|---------------|--------|------------------------|
| `backend/app/main.py` | add 4 `app.include_router(...)` calls (KPI, tenant-config admin, public branding) + the deferred-import block at lines 180-184 | the existing `app.include_router(...)` block (lines 186-197) and the `# noqa: E402` deferred-import block (lines 180-184) |

### Frontend — NEW

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `frontend/src/app/admin/page.tsx` (replace placeholder) | page (Server Component) | request-response | `frontend/src/app/admin/users/page.tsx` (`async` Server Component, `fetch*` via `"use server"` action, `force-dynamic`, try/catch degrade, `max-w-6xl px-6 py-12`) | exact |
| `frontend/src/components/admin/kpi-card.tsx` (`KpiCard` + `KpiGrid`) | component | — | `frontend/src/components/admin/recharge-form.tsx` (shadcn import style, `tabular-nums`) + `card.tsx` primitive (UI-SPEC §Component Inventory) | role-match |
| `frontend/src/components/admin/dau-window-toggle.tsx` (`DauWindowToggle`) | component | — | `frontend/src/components/price-history-chart.tsx` `WindowToggle` (lines 46-75 — `flex gap-1`, `h-11`, `variant`/`aria-pressed`) | exact |
| `frontend/src/components/admin/volume-chart.tsx` (`VolumeChart` + empty state) | component | — | `frontend/src/components/price-history-chart.tsx` (entire file — `"use client"`, `ResponsiveContainer` in `h-64`, `<2 points` empty state at same height) | exact (swap `LineChart`→`AreaChart`, `probability`→`volume`) |
| `frontend/src/app/admin/branding/page.tsx` | page (Server Component) | request-response | `frontend/src/app/admin/users/page.tsx` (Server Component fetching current persisted values via `"use server"` action) | exact |
| `frontend/src/components/admin/branding-form.tsx` (`BrandingForm`, `ColorField`, `LogoUploadField`) | component | — | `frontend/src/components/admin/recharge-form.tsx` (entire file — RHF+zod, `FormField`/`FormMessage`, `Loader2` submit spinner, sonner toast) | exact |
| `frontend/src/lib/branding-api.ts` (or extend `lib/admin-api.ts` + `lib/api.ts`) | lib | request-response | `frontend/src/lib/admin-api.ts` (`"use server"` Bearer-forward for the admin CRUD legs) **+** `frontend/src/lib/api.ts` (public `apiBase()` + `cache:"no-store"` for `/branding/current`) | exact |

### Frontend — MODIFY

| Modified File | Change | Analog for the change |
|---------------|--------|------------------------|
| `frontend/src/app/layout.tsx` | make `async`, `await` public `/branding/current`, inject `<style>:root{--brand-*}</style>` | `frontend/src/app/admin/users/page.tsx` (async Server Component fetch + try/catch degrade) + the `<style>` block pattern in RESEARCH §runtime theming |
| `frontend/src/app/globals.css` | add `--brand-primary`/`--brand-secondary` to `:root` + map via `@theme inline` | the existing `:root` + `@theme inline` block (lines 4-12) |
| `frontend/src/components/admin/admin-nav.tsx` | add `Dashboard` (leading) + `Branding` links to `LINKS` array | the `LINKS` array (lines 19-22) + active/inactive `cn(...)` styling (lines 37-41) |

### Tests — NEW (Wave 0)

| New Test File | Role | Analog | Match Quality |
|---------------|------|--------|---------------|
| `backend/tests/admin/test_tenant_config_negative.py` | test (403/401 negative) | `backend/tests/admin/test_auth_negative.py` (entire file — `_routes()` list, `seed_user(is_superuser=False)`, 401/403 assertions) | exact (swap `_routes()` for the tenant-config GET/PUT) |
| `backend/tests/admin/test_kpi.py` | test (integration) | `backend/tests/admin/_helpers.py` seed helpers + settlement test seams (P&L net, DAU UNION, pending predicate) | role-match |
| `backend/tests/admin/test_tenant_config.py` | test (integration) | `backend/tests/admin/_helpers.py` (admin Bearer + PUT) — bad hex 422, oversize logo 422, valid round-trip | role-match |
| `backend/tests/branding/test_branding_public.py` | test (integration) | public market tests + `_helpers.client()` (no-auth GET `/branding/current` + `/branding/logo`) | role-match |
| `frontend/src/components/admin/volume-chart.test.tsx` + KPI/form tests | test (vitest) | `frontend/src/components/price-history-chart.test.tsx` (entire file — `ResizeObserver` stub, `getBoundingClientRect` stub, react-is sentinel `svg path` assertion, empty-state copy, toggle) | exact |

---

## Pattern Assignments

### `backend/app/branding/admin_router.py` (router, CRUD) — admin tenant-config

**Analog:** `backend/app/wallet/admin_router.py` (audit + MissingGreenlet capture) and `backend/app/admin/router.py` (GET/PUT + commit-then-return).

**Header — `from __future__` MUST be ABSENT** (`wallet/admin_router.py` lines 22-26 document why): FastAPI's `Annotated[T, Depends(...)]` resolver on Python 3.13 breaks with forward-ref strings → params misread as query params → 422.

**Imports + router decl** (`wallet/admin_router.py` lines 28-46):
```python
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_active_admin
from app.auth.models import User
from app.core.audit.service import AuditService
from app.db.session import get_async_session

tenant_config_admin_router = APIRouter(prefix="/api/v1/admin/tenant-config", tags=["admin-branding"])
```

**Admin gate on every endpoint** (`admin/router.py` lines 49-52):
```python
@tenant_config_admin_router.get("", response_model=TenantConfigRead)
async def get_tenant_config(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
) -> TenantConfigRead: ...
```

**PUT — capture `admin.id` BEFORE any commit (MissingGreenlet trap)** (`wallet/admin_router.py` lines 70-76, 158-169):
```python
admin_id = admin.id  # plain value NOW — a later commit expires the ORM instance
# ... validate + persist the single row ...
await AuditService.record(
    session,
    actor=f"user:{admin_id}",
    event_type="admin.branding_updated",
    payload={"primary_hex": body.primary_hex, "secondary_hex": body.secondary_hex, ...},
)
await session.commit()
```
> Use `AuditService.record(...)` then `session.commit()` — never raw `INSERT INTO audit_log` (`core/audit/service.py` is the sole writer; it `flush()`es, the caller commits).

**Validation rejection → 422** comes from the schema (`extra="forbid"` + `Field(pattern=...)`); raise `HTTPException(status_code=422, ...)` for logo size/content-type rejections that pydantic can't express (mirror `wallet/admin_router.py` 400-branch shape, lines 133-144).

---

### `backend/app/branding/router.py` (router, request-response) — public branding

**Analog:** `backend/app/markets/router.py` `public_market_router` (public, no admin dep) for `GET /branding/current`; a raw-bytes `Response` for `GET /branding/logo`.

- **No auth dependency** on either endpoint (D-12: branding is public). Just `session: Annotated[AsyncSession, Depends(get_async_session)]`.
- `GET /branding/current` → small JSON: `{ brand_name, primary_hex, secondary_hex, logo_url }` (Pitfall 7 — do NOT base64-inline the logo here).
- `GET /branding/logo` → `from fastapi import Response; return Response(content=logo_bytes, media_type=content_type, headers={"X-Content-Type-Options": "nosniff"})` (Security §SVG/logo threat). `from __future__` ABSENT (same router rule).

---

### `backend/app/admin/kpi_service.py` (service, read-only aggregates)

**Analog:** `backend/app/wallet/service.py` `get_transactions` (lines 436-488) for the `entries`→`transfers` join + `select(func.count()).select_from(...)`; `backend/app/core/audit/router.py` (lines 70-71) for the count-over-subquery used by the DAU UNION.

**Entries+Transfers join shape (House P&L — reuse this exact join)** (`wallet/service.py` lines 471-486):
```python
select(... )
    .select_from(Entry).join(Transfer, Entry.transfer_id == Transfer.id)
    .where(Transfer.kind.in_(("settle_loss","reverse_loss","settle_winnings","reverse_winnings")))
```
Use the kind constants from `app/settlement/constants.py` (`TRANSFER_SETTLE_LOSS`, `TRANSFER_SETTLE_WINNINGS`, `TRANSFER_REVERSE_LOSS`, `TRANSFER_REVERSE_WINNINGS`) — do NOT hardcode strings. House P&L = `Σ(settle_loss credits to house_revenue) − Σ(settle_winnings debits from house_promo)`, with `reverse_*` netted. Account UUIDs `HOUSE_REVENUE_ACCOUNT_ID` / `HOUSE_PROMO_ACCOUNT_ID` from `app/wallet/constants.py` for the index-friendly arm. (See RESEARCH §Flagged Unknown 1 for the locked SQL — `SUM(house_revenue) - SUM(house_expense)` is NOT implementable; there is no `house_expense` account.)

**Count-over-subquery shape (DAU UNION)** (`core/audit/router.py` lines 70-71):
```python
count_stmt = select(func.count()).select_from(base.subquery())
total = (await session.execute(count_stmt)).scalar_one()
```
DAU = `COUNT(*)` over `select(Bet.user_id).where(Bet.created_at >= lo).union(select(split_part(AuditLog.actor,':',2)::uuid).where(AuditLog.event_type == "auth.session_started", AuditLog.occurred_at >= lo, AuditLog.actor.like("user:%"))).subquery()`. The login event name is `auth.session_started` (VERIFIED `app/auth/router.py:176`) — NOT `auth.login_started` (that literal in `KNOWN_EVENT_TYPES` is stale, confirmed `core/audit/schemas.py:32`). Bets emit NO audit event, so the UNION with `bets` is mandatory (RESEARCH §Flagged Unknown 2).

**Other KPI predicates (VERIFIED against `markets/models.py` + `bets/models.py`):**
- Active markets: `COUNT(Market WHERE status == "OPEN")` (`MarketStatus.OPEN`, `markets/enums.py`).
- Pending resolutions: `COUNT(Market WHERE deadline < now() AND status NOT IN ('RESOLVED','CANCELLED','DRAFT'))` — single `deadline` column for both sources (no `endDate` column exists).
- 24h volume: `COALESCE(SUM(Bet.stake), 0) WHERE Bet.created_at >= now()-24h` — use `bets.stake`, NOT `markets.volume`/`volume_24hr` (those are Polymarket replication fields).
- 30-day chart buckets: `date_trunc('day', Bet.created_at) GROUP BY day` → `[{day, volume:str}]`.

All money results are `Decimal` → serialize via `MoneyStr` in the schema (never float).

---

### `backend/app/branding/models.py` (model, CRUD) — `TenantConfig`

**Analog:** `backend/app/markets/models.py` `Market` class (String-column + CHECK, `tenant_id` ghost lines 125-129, timestamps).

```python
from __future__ import annotations  # OK in models (only routers forbid it)
# ... Base, get_settings, Money not needed; bytes via LargeBinary
class TenantConfig(Base):
    __tablename__ = "tenant_config"
    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
        default=uuid4, server_default=func.gen_random_uuid())
    brand_name: Mapped[str] = mapped_column(Text, nullable=False)
    primary_hex: Mapped[str] = mapped_column(String(7), nullable=False)     # '#rrggbb'
    secondary_hex: Mapped[str] = mapped_column(String(7), nullable=False)
    logo_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # base64/bytes in-row (D-08)
    logo_content_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at / updated_at: DateTime(timezone=True), server_default=func.now() (updated_at: onupdate=func.now())  # mirror Market lines 104-112
    tenant_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True), nullable=True,
        default=lambda: get_settings().TENANT_ID_DEFAULT)   # ghost — VERBATIM from Market lines 125-129
    __table_args__ = (UniqueConstraint("tenant_id", name="tenant_config_tenant_id_key"),)  # single-row → one-per-tenant seam (D-07)
```

---

### `backend/alembic/versions/0009_phase10_tenant_config.py` (migration, single head)

**Analogs:** `0008_phase8_user_created_at.py` (revision header shape) + `0004_phase3_wallet_ledger.py` (table create + idempotent singleton seed).

**Revision header — chain off the single current head** (`0008` lines 26-29):
```python
revision: str = "0009_phase10_tenant_config"
down_revision: str | None = "0008_phase8_user_created_at"   # VERIFIED single head
branch_labels: str | None = None
depends_on: str | None = None
```
> Single-head chain VERIFIED: 0001→0002→0003_markets→[0004_wallet & 0004_polymarket]→0005→0006_merge→0007→**0008** (head). Do NOT create a second head.

**Singleton seed (idempotent)** (`0004` lines 228-237 pattern — `ON CONFLICT DO NOTHING`):
```python
TENANT_DEFAULT = "00000000-0000-0000-0000-000000000001"  # same literal as 0001/0002/0004 (Pitfall 10)
op.execute(f"""
  INSERT INTO tenant_config (id, brand_name, primary_hex, secondary_hex, tenant_id) VALUES
    (gen_random_uuid(), 'XPredict', '#4f46e5', '#0ea5e9', '{TENANT_DEFAULT}'::uuid)
  ON CONFLICT (tenant_id) DO NOTHING;
""")
```
Column DDL mirrors `0004` `op.create_table` style (postgresql.UUID, `sa.Text`, `sa.LargeBinary`, `sa.TIMESTAMP(timezone=True) server_default NOW()`, `tenant_id` with `server_default '<TENANT_DEFAULT>'::uuid`).

---

### `backend/app/branding/schemas.py` (schema, request-response)

**Analogs:** `backend/app/admin/schemas.py` (`extra="forbid"`, `from_attributes`, `MoneyStr` reuse) + `markets/schemas.py` `MarketCreate` (field validator).

```python
from pydantic import BaseModel, ConfigDict, Field

_HEX = r"^#[0-9a-fA-F]{6}$"   # server-side hex allowlist (D-09, Pitfall 5 <style>-injection guard)

class TenantConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")          # 422 on stray field — VERBATIM admin/schemas.py BanRequest
    brand_name: str = Field(min_length=1, max_length=120)
    primary_hex: str = Field(pattern=_HEX)
    secondary_hex: str = Field(pattern=_HEX)
    # logo handled out-of-band (multipart/UploadFile) — size cap + content-type allowlist validated in the router

class TenantConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)    # VERBATIM admin/schemas.py UserListItem line 51
    brand_name: str
    primary_hex: str
    secondary_hex: str
    logo_url: str | None = None

class BrandingPublic(BaseModel):   # the public /branding/current payload — small, no bytes (Pitfall 7)
    brand_name: str
    primary_hex: str
    secondary_hex: str
    logo_url: str | None = None
```
> No money fields here. If a KPI schema needs money, import `from app.wallet.schemas import MoneyStr` (VERBATIM `admin/schemas.py` line 29) and type every Decimal as `MoneyStr`.

---

### `backend/app/admin/kpi_schemas.py` (schema) — KPI payload

**Analog:** `admin/schemas.py` (`MoneyStr` fields) + `markets/schemas.py` `PriceHistoryResponse`/`PricePoint` (lines 152-178 — bucket-list shape, money/odds as string via serializer).

```python
from app.wallet.schemas import MoneyStr   # money-as-string (CI money-lint enforced)

class VolumeBucket(BaseModel):
    day: datetime
    volume: MoneyStr

class KpiResponse(BaseModel):
    volume_24h: MoneyStr
    daily_active_users: int
    active_markets: int
    pending_resolutions: int
    house_pnl_today: MoneyStr        # may be NEGATIVE (valid) — string
    house_pnl_cumulative: MoneyStr
    volume_buckets: list[VolumeBucket]   # ≤30 daily points; <1 → frontend empty state
```

---

### `backend/app/main.py` (modify) — wire routers

**Analog:** existing include block (lines 186-197) + deferred-import block (lines 180-184, `# noqa: E402`).
Add to the deferred-import block and call `app.include_router(...)` for: KPI router, tenant-config admin router (admin prefix), public branding router. Keep the established ordering (admin routers grouped, public last).

---

### `frontend/src/app/admin/page.tsx` (modify, page) — KPI dashboard

**Analog:** `frontend/src/app/admin/users/page.tsx` (entire file).

```tsx
export const dynamic = "force-dynamic";   // VERBATIM users/page.tsx line 16

export default async function AdminHomePage() {
  let kpis: KpiResponse;
  try {
    kpis = await fetchKpis({ window: "24h" });   // "use server" Bearer-forwarded action (see lib pattern)
  } catch {
    // degrade — render the KPI-load-error copy, not a crash (mirror users/page.tsx try/catch lines 20-29)
  }
  return (
    <div className="mx-auto max-w-6xl px-6 py-12">   {/* VERBATIM admin shell width */}
      <h1 className="text-3xl font-semibold tracking-tight">Dashboard</h1>
      <KpiGrid kpis={kpis} />
      <VolumeChart buckets={kpis.volume_buckets} />
    </div>
  );
}
```
The DAU window toggle is interactive → its refetch happens client-side; pass the initial server-fetched payload down and let the toggle re-call the action with `?window=` (mirror the price-history parent owning window state, RESEARCH).

---

### `frontend/src/components/admin/volume-chart.tsx` (component) — Recharts volume chart

**Analog:** `frontend/src/components/price-history-chart.tsx` (entire file — copy structure, swap `LineChart`→`AreaChart`).

**Mandatory gotchas (copy verbatim):**
- `"use client"` (line 22).
- Fixed-height parent `<div className="h-64 w-full">` wrapping `<ResponsiveContainer width="100%" height="100%">` (lines 104-106) — collapses to 0 otherwise.
- `<2 buckets` (here: `<1`) → empty state at the SAME `h-64` (lines 77-89, 101-102) — no layout jump.
- Money string → display only via `parseFloat`/`Math.round` inside `data.map` (lines 108-112); never store as float.
- Stroke/fill: `var(--brand-primary)` (re-skins with branding) or `#059669` emerald (UI-SPEC A-CHART). Series key `volume`, X axis `day`.
- `react-is` stays pinned via `pnpm.overrides` — do NOT touch (renders blank on React 19 otherwise).

---

### `frontend/src/components/admin/dau-window-toggle.tsx` (component)

**Analog:** `price-history-chart.tsx` `WindowToggle` (lines 46-75) — copy nearly verbatim.
`flex gap-1` `role="group"`, each `<Button size="sm" variant={active?"secondary":"ghost"} aria-pressed={active} className={cn("h-11", active && "font-semibold")}>`. Windows `["24h","7d","30d"]`, default `24h` (D-05). `h-11` = 44px touch target.

---

### `frontend/src/components/admin/branding-form.tsx` (component) — branding form

**Analog:** `frontend/src/components/admin/recharge-form.tsx` (entire file).

Copy: `"use client"` + RHF + `zodResolver` + zod schema (lines 18-67); `Form`/`FormField`/`FormItem`/`FormLabel`/`FormControl`/`FormMessage` (lines 28-36); submit `Loader2` spinner + `disabled` while pending (lines 80-109, 165-174); `toast.success`/`toast.error` (lines 101, 105). Zod hex mirror `z.string().regex(/^#[0-9a-fA-F]{6}$/, "Enter a valid hex color, e.g. #4F46E5.")` (server is authoritative — D-09). On 422 map field errors to inline `FormMessage`. Submit button is the default (non-destructive) variant — copy "Save branding" (UI-SPEC A-SAVE). `ColorField` adds a live swatch `<div>` reflecting the input; `LogoUploadField` uses `<Input type="file">` + `<img>` object-URL preview.

---

### `frontend/src/app/layout.tsx` (modify, layout) — runtime theming injection

**Analog:** `admin/users/page.tsx` (async Server Component + try/catch degrade) + RESEARCH §runtime theming `<style>` block.

```tsx
export default async function RootLayout({ children }) {
  let b = { primary_hex: "#4f46e5", secondary_hex: "#0ea5e9" };   // safe fallback (UI-SPEC A-FALLBACK)
  try { b = await fetchBrandingPublic(); } catch {}                // per-navigation, cache:"no-store" → no rebuild (SC#5)
  return (
    <html lang="en" className="h-full antialiased">
      <head>
        {/* hex is server-validated ^#[0-9a-fA-F]{6}$ BEFORE persist AND injection — Pitfall 5 / threat: stored CSS injection */}
        <style>{`:root{--brand-primary:${b.primary_hex};--brand-secondary:${b.secondary_hex};}`}</style>
      </head>
      <body className="min-h-full flex flex-col">{children}<Toaster /></body>
    </html>
  );
}
```
Keep `<Toaster />` (current line 19). Brand name + `<img src="/branding/logo">` consumed from the same payload in the player header.

---

### `frontend/src/app/globals.css` (modify) — brand tokens

**Analog:** the existing `:root` + `@theme inline` block (lines 4-12).
```css
:root {
  --background: #ffffff;
  --foreground: #171717;
  --brand-primary: #4f46e5;       /* indigo/sky fallback (UI-SPEC A-FALLBACK) */
  --brand-secondary: #0ea5e9;
}
@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-brand-primary: var(--brand-primary);     /* → bg-brand-primary / text-brand-primary */
  --color-brand-secondary: var(--brand-secondary);
}
```

---

### `frontend/src/components/admin/admin-nav.tsx` (modify)

**Analog:** the `LINKS` array (lines 19-22) + active `cn(...)` styling (lines 37-41).
Prepend `{ href: "/admin", label: "Dashboard" }` as the leading entry and add `{ href: "/admin/branding", label: "Branding" }`. Reuse the existing active/inactive `cn(...)` block unchanged. Note: `/admin` active-match needs an exact check (`pathname === "/admin"`) since `startsWith("/admin/")` would mark it active on every sub-route.

---

### `frontend/src/lib/branding-api.ts` + KPI helpers (lib)

**Analogs:** `frontend/src/lib/admin-api.ts` (admin Bearer-forward) + `frontend/src/lib/api.ts` (public fetch).

- **Admin KPI + tenant-config PUT/GET** → add to a `"use server"` module like `admin-api.ts`: `adminApiFetch(path, init)` reads the `admin_jwt` HttpOnly cookie via `cookies()` and forwards `Authorization: Bearer <token>` (lines 44-73). **This resolves RESEARCH open-question A6** — admin SSR token-forwarding already exists; reuse `adminApiFetch` for `GET /api/v1/admin/dashboard/kpis` and the tenant-config CRUD. Token never reaches client JS.
- **Public `/branding/current`** → a non-`"use server"` helper using `apiBase()` (server: `BACKEND_URL`; browser: `NEXT_PUBLIC_API_URL`) + `cache:"no-store"` + typed throw on `!res.ok` (`api.ts` lines 87-112). The root layout calls this (no auth).

---

### `backend/tests/admin/test_tenant_config_negative.py` (test) — SC#6 403

**Analog:** `backend/tests/admin/test_auth_negative.py` (entire file).
Copy verbatim, swapping `_routes()` (lines 28-37) for the tenant-config routes:
```python
def _routes() -> list[tuple[str, str, dict | None]]:
    return [
        ("GET", "/api/v1/admin/tenant-config", None),
        ("PUT", "/api/v1/admin/tenant-config", {"brand_name":"x","primary_hex":"#000000","secondary_hex":"#ffffff"}),
    ]
```
Keep the two tests: 401 without token, 403 with player Bearer (`seed_user(is_superuser=False)`, lines 46-75 — including the "admin login itself rejects the player → 400/401 wall is acceptable" branch). `_call` must add a `PUT` branch.

---

## Shared Patterns

### Admin Bearer auth gate
**Source:** `backend/app/auth/deps.py` (`current_active_admin` re-export, lines 82-92) used in `backend/app/wallet/admin_router.py:53`.
**Apply to:** every new `/admin/*` endpoint (KPI router, tenant-config admin router) — NOT the public `/branding/*` router.
```python
from app.auth.deps import current_active_admin
admin: Annotated[User, Depends(current_active_admin)],
```

### No `from __future__ import annotations` in routers
**Source:** documented in `wallet/admin_router.py` (lines 22-26), `admin/router.py` (lines 17-22), `core/audit/router.py` (lines 20-22).
**Apply to:** ALL new router files (`branding/admin_router.py`, `branding/router.py`, `admin/kpi_router.py`). It IS used in models / schemas / services / migrations (those are fine).

### Money-as-string (`MoneyStr`)
**Source:** `backend/app/wallet/schemas.py` (`MoneyStr`, lines 36-39); reused via `from app.wallet.schemas import MoneyStr` in `admin/schemas.py:29`.
**Apply to:** every Decimal field in KPI/branding schemas (`volume_24h`, `house_pnl_*`, bucket `volume`). CI `scripts/lint_money_columns.py` + a money-lint enforce this. Frontend renders strings via `formatVolume`/string ops, never `parseFloat`/`Number()` for storage (`api.ts` lines 194-213).

### `tenant_id` ghost column
**Source:** `Market` (`markets/models.py` lines 125-129), `Account` (`wallet/models.py` lines 100-105), `AuditLog` (`core/audit/models.py` lines 48-52) — all identical.
**Apply to:** `TenantConfig` model + its migration (`server_default '<TENANT_DEFAULT>'::uuid`). `default=lambda: get_settings().TENANT_ID_DEFAULT`.

### `extra="forbid"` request schemas
**Source:** `RechargeRequest` (`wallet/schemas.py:52`), `BanRequest` (`admin/schemas.py:89`).
**Apply to:** `TenantConfigUpdate` (a stray field → hard 422).

### Audit admin mutations
**Source:** `AuditService.record(...)` then `session.commit()` (`wallet/admin_router.py:158-169`); `AuditService` is the SOLE writer (`core/audit/service.py`).
**Apply to:** the tenant-config PUT → `event_type="admin.branding_updated"`, `actor=f"user:{admin_id}"` (capture `admin_id` BEFORE any commit — MissingGreenlet, `wallet/admin_router.py:70-76`). Optional nicety: add `admin.branding_updated` to `KNOWN_EVENT_TYPES` (`core/audit/schemas.py:30-50`).

### Server-Component fetch + admin token forwarding
**Sources:**
- Public read: `frontend/src/lib/api.ts` `apiBase()` + `fetch(..., {cache:"no-store"})` (lines 87-112) — for `/branding/current` in the root layout.
- Admin read/write: `frontend/src/lib/admin-api.ts` `"use server"` `adminApiFetch` reading `admin_jwt` cookie → `Authorization: Bearer` (lines 44-73) — for KPI + tenant-config. **(Resolves A6.)**
**Apply to:** KPI dashboard page, branding form/page, root layout.

### Recharts in a sized parent (react-is pin)
**Source:** `frontend/src/components/price-history-chart.tsx` (lines 104-135) + test stub `price-history-chart.test.tsx` (lines 21-56).
**Apply to:** `VolumeChart` — `h-64` parent, empty state at same height, react-is untouched. The vitest must stub `ResizeObserver` + `getBoundingClientRect` and assert `svg path.recharts-*` (react-is sentinel).

### Count-over-subquery + entries/transfers join (KPI aggregates)
**Source:** `wallet/service.py` `get_transactions` (lines 464-486) and `core/audit/router.py` (lines 59-71).
**Apply to:** the KPI service P&L join (entries→transfers, kind filter) and DAU `select(func.count()).select_from(union_subquery)`.

---

## No Analog Found

None. Every file in scope mirrors an existing, in-repo pattern. The only genuinely new SHAPES (still grounded in existing primitives) are:
- a **single-row** table (`UniqueConstraint(tenant_id)` is the one novel constraint — column/ghost/timestamp shape is identical to `Market`),
- a **raw-bytes `Response`** for `GET /branding/logo` (FastAPI `Response(content=bytes, media_type=...)` — standard FastAPI, no in-repo precedent for serving binary, but trivial),
- a **`<style>`-injection** in the root layout (RESEARCH §runtime theming gives the exact snippet; security guard = server-side hex regex).

---

## Locked Findings the Planner MUST Honor (verified this session)

| Topic | Locked value | Verified at |
|-------|--------------|-------------|
| Login audit event | `auth.session_started` (NOT `auth.login_started`) | `app/auth/router.py:176`; `KNOWN_EVENT_TYPES` is stale (`core/audit/schemas.py:32`) |
| Bets audit | Bets emit NO audit event → DAU MUST UNION `bets` + logins | `bets/constants.py` (`TRANSFER_BET_PLACED` is a transfer kind, not an event); no `AuditService` import in `app/bets/` |
| House P&L | net `settle_loss`/`reverse_loss` (credit→`house_revenue`) − `settle_winnings`/`reverse_winnings` (debit→`house_promo`); NO `house_expense` account exists | `settlement/constants.py` lines 16-37; `settlement/service.py` docstring lines 11-22; `wallet/constants.py` (3 kinds only) |
| Single Alembic head | `0008_phase8_user_created_at` | `grep down_revision` across `alembic/versions` |
| Pending resolutions | single `markets.deadline` column for both sources; no `endDate` | `markets/models.py:94`; `0004_phase6_polymarket_sync` added only volume fields |
| Active markets | `status == "OPEN"` (String(20) + CHECK) | `markets/models.py:89-93`, `markets/enums.py` |
| 24h volume | `SUM(bets.stake)` — NOT `markets.volume`/`volume_24hr` | `bets/models.py:52`; volume fields are Polymarket replication |
| Admin SSR auth (A6) | reuse `lib/admin-api.ts` `adminApiFetch` (`admin_jwt` cookie → Bearer) | `frontend/src/lib/admin-api.ts:44-73` |
| Next version | Next.js `^16.2.6` (not 15) | RESEARCH §Standard Stack `[VERIFIED: package.json]` |

---

## Metadata

**Analog search scope:** `backend/app/{wallet,admin,markets,bets,settlement,auth,core/audit,db}`, `backend/alembic/versions`, `backend/tests/admin`, `frontend/src/{app,components,lib}`.
**Files scanned/read:** ~30 (all analogs verified, not assumed).
**Pattern extraction date:** 2026-05-31
