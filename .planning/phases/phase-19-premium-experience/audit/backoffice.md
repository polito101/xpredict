# Phase 19 Audit — Backoffice / Admin Surface + White-Label Branding

Area: Backoffice / admin surface (`/admin/*`) + the white-label runtime branding pipeline.
Scope: read-only inventory of the admin information architecture, the CRUD + settlement dialog
flows, and the COMPLETE end-to-end branding pipeline (admin form → endpoint → persist → player
re-skin). All paths are relative to repo root unless noted.

---

## 1. Admin Information Architecture

### 1.1 Shell / layout

- `frontend/src/app/admin/layout.tsx` — **Server Component**, wraps every `/admin/*` route
  (incl. `/admin/login`). Renders a top `<nav>` (hardcoded wordmark **"XPredict Admin"** linking
  to `/admin`, + the `<AdminNav>` link cluster) and a footer (ToS / Token-policy links + the
  "Play-money tokens have no monetary value." disclaimer). Hardcoded palette:
  `bg-zinc-50 dark:bg-zinc-950` page, `bg-white dark:bg-zinc-900` nav/footer,
  `border-zinc-200 dark:border-zinc-800`. **The wordmark here is a static string — it does NOT
  consume the operator brand name or logo** (unlike the player header). Pure-presentational, safe
  to restyle; does not enforce auth (middleware + FastAPI `current_active_admin` are the gates).
- `frontend/src/components/admin/admin-nav.tsx` — `"use client"` (needs `usePathname()` for active
  state). The nav model is a hardcoded `LINKS` array:
  `Dashboard (/admin, exact)`, `Users`, `Markets`, `Events`, `Audit log`, `Branding` + a trailing
  `Log out` link to `/admin/logout`. Active style: `font-semibold text-zinc-900 underline
  underline-offset-4 dark:text-zinc-50`; inactive `text-zinc-500 hover:text-zinc-900`.
  Pure-presentational nav; restyle-safe. (Note: `/admin` uses an EXACT match; others use
  `startsWith` prefix — preserve that logic on restyle.)
- `frontend/src/app/admin/loading.tsx` — dashboard Suspense skeleton (5 KPI cards + chart). Mirrors
  the dashboard layout to avoid layout shift. Restyle-safe.

### 1.2 Sections (one row per nav entry)

| Route | File | Render model | Restyle class |
|-------|------|--------------|---------------|
| `/admin` (Dashboard) | `app/admin/page.tsx` | Server: `await fetchKpis("24h")` → `<KpiDashboard>`; degrades to copy on null | pure-presentational shell |
| `/admin/users` | `app/admin/users/page.tsx` | Server: `fetchUsers(page1)` → `<UsersDataTable>`; empty on fail | shell + logic-coupled table |
| `/admin/users/[id]` | `app/admin/users/[id]/page.tsx` + `user-detail-tabs.tsx` | Server fetch detail → client island (header + Profile/Wallet/Bets tabs + ban/unban dialogs) | logic-coupled island |
| `/admin/markets` | `app/admin/markets/page.tsx` | Server: `fetchMarkets(page1)` → `<MarketsDataTable>`; "Create market" CTA | shell + logic-coupled table |
| `/admin/markets/new` | `app/admin/markets/new/page.tsx` | `<MarketForm mode="create">` | logic-coupled form |
| `/admin/markets/[id]` | `app/admin/markets/[id]/page.tsx` + `market-detail-actions.tsx` | Server fetch → island (edit form + 4 gated settlement dialogs) | logic-coupled island |
| `/admin/events` | `app/admin/events/page.tsx` | Server: `fetchCatalog()` filtered to `type:event && source:HOUSE` (NO dedicated admin list endpoint) — raw `<table>`, not TanStack | mostly-presentational table |
| `/admin/events/new` | `app/admin/events/new/page.tsx` | `<EventForm mode="create">` (dynamic outcomes) | logic-coupled form |
| `/admin/events/[slug]` | `app/admin/events/[slug]/page.tsx` + `event-detail-admin-actions.tsx` | Server `fetchEvent(slug)` → island (edit + resolve/void/reverse) | logic-coupled island |
| `/admin/audit-log` | `app/admin/audit-log/page.tsx` | Server: `fetchAuditLog(page1, size50)` + `fetchAuditEventTypes()` → `<AuditLogTable>` (READ-ONLY) | shell + logic-coupled table |
| `/admin/branding` | `app/admin/branding/page.tsx` | Server `fetchTenantConfig()` (degrades to XPredict defaults) → `<BrandingForm>` | logic-coupled form |
| `/admin/login` | `app/admin/login/page.tsx` + `admin-login-form.tsx` | centered `<Card>` + form, distinct "Admin sign in" heading | logic-coupled form |

**Common page chrome (consistent across every section):** `mx-auto max-w-6xl px-6 py-12` container;
H1 either `text-xl font-semibold tracking-tight` (list pages) or `text-3xl ...` (dashboard + detail
pages — inconsistent, worth normalizing); `dynamic = "force-dynamic"` everywhere; every Server
Component wraps its fetch in try/catch and degrades to empty/defaults rather than crashing.

---

## 2. CRUD + Settlement Dialog Flows

### 2.1 API helper layer (Server Actions, Bearer-forwarding)

All four admin API libs are `"use server"` modules that read the **HttpOnly `admin_jwt` cookie**
server-side via `next/headers > cookies()` and forward it as `Authorization: Bearer <token>`. The
token never reaches client JS. They throw `Error("API error: <status>")` on non-2xx (status preserved
in the message so callers can branch). `BACKEND_URL` is server-only (no `NEXT_PUBLIC_` leak).

- `lib/admin-api.ts` — users CRM + audit + recharge + CSV export. Endpoints (all under
  `/api/v1/admin` EXCEPT recharge):
  - `GET /users{qs}` → `PaginatedResponse<UserListItem>`
  - `GET /users/{id}` → `UserDetail`
  - `GET /users/{id}/transactions{qs}` → `PaginatedResponse<UserTransactionItem>`
  - `GET /users/{id}/bets{qs}` → `PaginatedResponse<UserBetItem>`
  - `POST /users/{id}/ban` body `{reason}` (required) → `UserDetail`
  - `POST /users/{id}/unban` body `{reason?}` → `UserDetail`
  - `POST /admin/wallets/{id}/recharge` body `{amount, reason}` + header `Idempotency-Key` (UUID v4)
    — **NOTE: BARE `/admin` prefix, NOT `/api/v1`** (the recharge prefix landmine).
  - `GET /api/v1/admin/audit-log{qs}` → `PaginatedResponse<AuditLogItem>`
  - `GET /api/v1/admin/audit-log/event-types` → `string[]`
- `lib/admin-markets-api.ts` — market CRUD + settlement. **THE TWO-PREFIX LANDMINE**: CRUD is at
  `/api/v1/admin/markets`, settlement is at the BARE `/admin/markets/{id}/...`:
  - `GET /api/v1/admin/markets{qs}` → `PaginatedResponse<MarketListItem>`
  - `GET /api/v1/admin/markets/{id}` → `MarketDetail`
  - `POST /api/v1/admin/markets` (MarketCreate) → `MarketDetail`
  - `PATCH /api/v1/admin/markets/{id}` (MarketUpdate) → `MarketDetail`
  - `POST /api/v1/admin/markets/{id}/close` (no body) → `MarketDetail`
  - `POST /admin/markets/{id}/resolve` `{winning_outcome_id, justification}` (bare prefix)
  - `POST /admin/markets/{id}/reverse` `{justification}` (bare prefix)
  - `POST /admin/markets/{id}/force-settle` `{winning_outcome_id, justification}` (bare prefix)
- `lib/admin-events-api.ts` — event CRUD + settlement, ALL at the BARE `/admin/events` prefix.
  resolve/void/reverse carry a `confirm` flag (`false` = non-mutating preview, `true` = execute,
  same `EventActionResponse`). `PATCH` after first child bet returns **HTTP 423** (edit-lock),
  decoded by `isEventLockedError`.
- `lib/branding-admin-api.ts` — covered fully in §3.
- `lib/admin-query.ts` — sync, client-usable query-string builders (`buildQuery`, `buildUsersQuery`).
- `lib/admin-format.ts` — display formatters. **MONEY DISCIPLINE: money is STRING end-to-end,
  formatted with string ops only — never `parseFloat`/`Number()`.** `formatMoney`, `formatSignedAmount`,
  `formatDate`, `formatTimestamp`, `formatRelativeTime`, `truncate`.

### 2.2 Backend contract confirmation (FastAPI)

- `backend/app/admin/router.py` — `admin_crm_router` prefix `/api/v1/admin`, 6 user endpoints, every
  one gated by `Depends(current_active_admin)`. `list_users` query params: page/page_size(≤100)/
  search/status(`^(active|banned)$`)/signup_after/signup_before/sort_by/sort_order(`^(asc|desc)$`).
- `backend/app/admin/kpi_router.py` — `kpi_router` prefix `/api/v1/admin/dashboard`, `GET /kpis` →
  `KpiResponse` (window query param).
- `backend/app/admin/export_router.py` — `admin_export_router` prefix `/api/v1/admin/export`, GET
  `/users`, `/transactions`, `/bets` (CSV; filename from Content-Disposition).
- `backend/app/core/audit/router.py` — `audit_admin_router` prefix `/api/v1/admin/audit-log`.

### 2.3 Settlement / destructive dialog flows (the operator's highest-risk actions)

All settlement dialogs are `"use client"`, built on shadcn `Dialog` + `Select` + `Textarea` + `Label`,
two-step (button reveals dialog → `destructive` confirm submits), keep the dialog OPEN during submit
(double-click guard), show a `Loader2` spinner, toast on success, and call an `on*` callback that does
`router.refresh()`. They share `components/admin/settlement-dialog-utils.ts` (`isSessionExpiredError`
→ 401/403 maps to the "session expired" toast). All are **logic-coupled** (props = ids/outcomes/
callbacks; restyle the inner markup but preserve state machine + validation).

- `resolve-market-dialog.tsx` — outcome `<Select>` + mandatory justification → `resolveMarket`.
- `force-settle-dialog.tsx` — same shape, for stuck Polymarket markets → `forceSettle`.
- `reverse-settlement-dialog.tsx` — justification → `reverseSettlement`.
- `close-market-dialog.tsx` — no-body close → `closeMarket`.
- `resolve-event-dialog.tsx` / `void-event-dialog.tsx` / `reverse-event-dialog.tsx` — event-group
  equivalents (preview via `confirm:false`, execute via `confirm:true`).
- `ban-confirm-dialog.tsx` / `unban-confirm-dialog.tsx` — user ban/unban (ban reason required).
- `recharge-form.tsx` — inline card form, generates `crypto.randomUUID()` Idempotency-Key, disabled
  for banned users.

**Action gating logic (must be preserved verbatim — restyle the buttons, not the gates):**
- `market-detail-actions.tsx`: Resolve (OPEN/CLOSED + HOUSE), Force-settle (OPEN/CLOSED + POLYMARKET),
  Reverse (RESOLVED), Close (OPEN). Edit form auto-locks `resolution_criteria` when `bet_count > 0`.
- `event-detail-admin-actions.tsx`: HOUSE-only mutations; mirrored (Polymarket) events render a
  read-only banner. Resolve (open/partially_resolved), Void (open only), Reverse (resolved/partial).

### 2.4 Data tables (TanStack Table v8, server-driven — logic-coupled)

`users-data-table.tsx`, `markets-data-table.tsx`, `audit-log-table.tsx` share one verbatim state
machine: `manualPagination`/`manualSorting`, a `firstRender` ref that skips the initial fetch (the
Server Component already provided page 1), `resetToFirstPage` on any filter change, rows-as-keyboard-
accessible-`role="link"` (markets/users), a 5-row `<Skeleton>` loading state, an empty state, and an
error state ("Failed to load data"). They use shadcn `Table/Select/Input/Tooltip/Skeleton` +
`PaginationControls`. **Restyle-safe at the cell/header/empty-state level; do NOT touch the fetch
effect, `firstRender` skip, or the column `accessorKey` set.** The audit log is explicitly READ-ONLY
(no mutation controls — D-11). Status chips: `market-status-badge.tsx` (5-state color map) and
`user-status-badge.tsx` (active=emerald / banned=red) — small pure-presentational chips with
hardcoded semantic colors + `aria-label`.

### 2.5 KPI dashboard (mostly presentational)

- `components/admin/kpi-dashboard.tsx` — `"use client"` wrapper owning the DAU window state +
  `fetchKpis` refetch in a transition. Logic-coupled (state + refetch).
- `components/admin/kpi-card.tsx` — `KpiCard` / `HousePnlCard` / `KpiGrid`. **Pure-presentational
  except the money formatting + sign-color rules**: `formatMoney`/`isNegativeMoney` are string-only;
  P&L colored `text-red-500` (negative) / `text-emerald-600` (≥0). Grid is `grid-cols-1 sm:2 lg:3`
  (5 cards). "Pending resolutions" card deep-links to `/admin/markets?status=CLOSED`. A real zero
  renders "$0.0000" (never em-dash) — preserve A-ZERO.
- `components/admin/volume-chart.tsx` — Recharts `AreaChart`. **Already brand-aware**: stroke/fill =
  `var(--brand-primary, #059669)` so it re-skins live. `react-is` is pinned to React 19 via
  pnpm.overrides (do NOT touch — Recharts renders blank otherwise). `parseFloat` here is DISPLAY-only.

---

## 3. White-Label Branding Pipeline (END-TO-END) — the load-bearing subsystem

### 3.1 Persistence model (single row, logo bytes in-row)

- `backend/app/branding/models.py` — `TenantConfig` table `tenant_config`, ONE row (v1 single-tenant;
  `UNIQUE(tenant_id)` + nullable `tenant_id` ghost = the v2 multi-tenant seam). Columns:
  `brand_name (Text)`, `primary_hex (String(7))`, `secondary_hex (String(7))`,
  `logo_bytes (LargeBinary, nullable)`, `logo_content_type (String(64), nullable)`, timestamps,
  `tenant_id`. **Logo bytes live IN THE ROW (D-08, no object storage) and are NEVER inlined into JSON.**
- `backend/app/branding/repo.py` — `load_singleton(session)` (ORDER BY created_at asc, deterministic
  even if the single-row invariant is violated) + `logo_url_for(row)` → `/branding/logo` or `None`.

### 3.2 Admin write path

1. **Form:** `components/admin/branding-form.tsx` (`BrandingForm`, `"use client"`). Fields:
   `brand_name` (Input), `primary_hex` + `secondary_hex` (`ColorField` = text Input + live swatch
   `<div>` whose `backgroundColor` reflects the value, falling back to `#f4f4f5` for invalid hex),
   and a logo file input (`LogoUploadField`-style) with an `<img>` object-URL preview. Client zod
   schema (UX only): `brand_name min 1`, hex `^#[0-9a-fA-F]{6}$`. Client logo pre-check: 256 KB cap
   + allowlist `png/jpeg/webp/svg+xml` (`LOGO_MAX_BYTES = 256*1024`). On submit →
   `updateTenantConfig`. Success toast: "Branding updated. Players see it on their next page load."
   422 → maps server field errors back to the right field via `parseBrandingApiError`; 401/403 →
   "session expired" toast. **Prop contract: `{ initial: TenantConfigRead }`. Logic-coupled** (form
   state + error mapping), but the visual chrome (labels, swatch, preview, save button) is fully
   restyle-safe. The Save button is the DEFAULT (brand-primary) variant — non-destructive.
2. **Server Action:** `lib/branding-admin-api.ts` (`"use server"`):
   - `fetchTenantConfig()` → `GET /api/v1/admin/tenant-config` (Bearer, no-store) → `TenantConfigRead`.
   - `updateTenantConfig(input)` → `PUT /api/v1/admin/tenant-config` as **multipart/form-data**
     (`brand_name` + `primary_hex` + `secondary_hex` + optional `logo` File). Content-Type is NOT set
     manually (FormData derives the boundary). Errors thrown as a JSON-encoded
     `BrandingApiError {status, fieldErrors}` so the form can recover structure across the action
     boundary.
3. **Backend:** `backend/app/branding/admin_router.py` — `tenant_config_admin_router` prefix
   `/api/v1/admin/tenant-config`, both endpoints gated by `Depends(current_active_admin)`.
   - `GET ""` → `TenantConfigRead` (404 if no row).
   - `PUT ""` validates `brand_name`/hex via `TenantConfigUpdate` (`extra="forbid"` + hex
     `Field(pattern=^#[0-9a-fA-F]{6}$)` → 422). Logo validated out-of-band: streamed read capped at
     `_MAX_LOGO_BYTES+1` (DoS guard), content-type allowlist + **magic-byte sniff** (PNG/JPEG/WebP;
     SVG accepted under cap only). Single row UPDATED in place (seeded if absent — never a duplicate
     insert). Mutation audited as `admin.branding_updated`, then committed. Returns `TenantConfigRead`
     with `logo_url = "/branding/logo"` if a logo exists else `null`.
   - Schemas: `backend/app/branding/schemas.py` — `TenantConfigUpdate` / `TenantConfigRead` /
     `BrandingPublic`.

### 3.3 Player read / re-skin path (THE CRITICAL "must not break" surface)

1. **Public endpoints:** `backend/app/branding/router.py` — `branding_router` (NO auth):
   - `GET /branding/current` → `BrandingPublic { brand_name, primary_hex, secondary_hex, logo_url }`
     (exactly 4 fields, NO bytes inlined). On a fresh/unseeded DB returns the XPredict indigo/sky
     defaults so the player UI never breaks.
   - `GET /branding/logo` → the stored bytes with stored Content-Type + `X-Content-Type-Options:
     nosniff` + `Content-Disposition: inline` + `Content-Security-Policy: default-src 'none'; sandbox`
     (SVG-in-`<img>` cannot run script). 404 when no logo.
2. **Fetch helper:** `lib/branding-public.ts` — plain module (NOT `"use server"`).
   `fetchBrandingPublic()` → `GET {apiBase}/branding/current` with **`cache: "no-store"`** (the
   per-navigation freshness contract — a palette change re-skins on the NEXT navigation, no rebuild).
   `apiBase()`: server-side uses `BACKEND_URL`; browser uses `NEXT_PUBLIC_API_URL`. Exposes
   `DEFAULT_BRANDING` (indigo `#4f46e5` / sky `#0ea5e9`) as the safe fallback.
3. **Injection point:** `frontend/src/app/layout.tsx` (player ROOT layout, async Server Component).
   On EVERY navigation it `await fetchBrandingPublic()` (catch → `DEFAULT_BRANDING`), then injects in
   `<head>`:
   ```
   <style>{`:root{--brand-primary:${b.primary_hex};--brand-primary-foreground:${pickReadableForeground(b.primary_hex)};--brand-secondary:${b.secondary_hex};}`}</style>
   ```
   Security (T-10-01): hexes are validated `^#[0-9a-fA-F]{6}$` server-side BEFORE persist AND before
   injection — a valid 6-digit hex can't contain `<`/`>`/`}`/quotes, so no `</style>` break-out. The
   layout interpolates ONLY the two validated hex tokens + the derived foreground (one of two constant
   literals) — never any other untrusted string.
4. **Token → Tailwind wiring:** `frontend/src/app/globals.css` defines `:root` defaults
   (`--brand-primary: #4f46e5`, `--brand-primary-foreground: #fafafa`, `--brand-secondary: #0ea5e9`)
   and maps them into Tailwind v4 via `@theme inline` as `--color-brand-primary`,
   `--color-brand-primary-foreground`, `--color-brand-secondary` → usable as `bg-brand-primary`,
   `text-brand-primary`, `border-brand-primary`, `bg-brand-secondary`. The injected `<style>` block
   OVERRIDES the `:root` defaults per navigation.
5. **Foreground derivation:** `lib/brand-color.ts` — `pickReadableForeground(hex)` returns `#fafafa`
   (dark brand) or `#18181b` (light brand) from WCAG relative luminance (0.179 cutoff). Keeps CTA text
   legible whatever palette the operator picks.
6. **Logo render:** `components/brand-logo.tsx` — `BrandLogo { brandName, logoUrl, className }`.
   Renders `<img src={NEXT_PUBLIC_API_URL + logoUrl} className="h-7 w-auto">` when a logo is set, else
   a wordmark = brand-color accent dot (`bg-brand-primary`) + the brand name text (zinc ink, fallback
   "XPredict"). Pure-presentational; logo bytes never inlined as markup.

### 3.4 Brand-token consumers across the PLAYER UI (the exact restyle blast radius)

Every place `--brand-primary`/`--brand-secondary` is consumed (`grep` confirmed):
- `components/ui/button.tsx` — DEFAULT variant `bg-brand-primary text-brand-primary-foreground
  hover:bg-brand-primary/90`; focus ring `ring-brand-primary`. **Every primary CTA platform-wide
  re-skins via this single primitive.** destructive=red, outline/secondary/ghost=zinc.
- `components/brand-logo.tsx` — accent dot `bg-brand-primary`.
- `components/catalog/event-card.tsx` — progress bar `bg-brand-primary`.
- `components/catalog/catalog-controls.tsx` — active filter `bg-brand-primary text-brand-primary-foreground`.
- `components/event/outcome-row.tsx` — selected `border-brand-primary ring-2 ring-brand-primary`; bar `bg-brand-primary`.
- `components/odds-display.tsx` — bar `bg-brand-primary`.
- `components/player-nav.tsx` — active link `text-brand-primary`.
- `components/price-history-chart.tsx` — line stroke `var(--brand-primary, #059669)`.
- `app/not-found.tsx` / `app/global-error.tsx` — accent text / button.
- `components/admin/volume-chart.tsx` — the ONLY admin consumer (chart stroke/fill).

---

## 4. What MUST NOT break when the player goes premium-dark

1. **The `<style>` injection contract in `app/layout.tsx`** must keep interpolating ONLY the two
   server-validated hexes + `pickReadableForeground(primary)`. Never concatenate other untrusted
   strings into that block (XSS guard T-10-01). A premium dark theme adds its OWN tokens; it must NOT
   remove or rename `--brand-primary` / `--brand-primary-foreground` / `--brand-secondary`.
2. **The Tailwind token mapping in `globals.css`** (`--color-brand-primary` etc.) and the utility
   names `bg-brand-primary` / `text-brand-primary` / `text-brand-primary-foreground` /
   `border-brand-primary` / `bg-brand-secondary` must survive — 10+ components reference them by name.
3. **`cache: "no-store"`** on `fetchBrandingPublic` — the per-navigation re-skin promise (SC#5).
   Static inlining / caching would break "operator changes palette → players see it next nav, no
   redeploy".
4. **`pickReadableForeground` must remain the source of `--brand-primary-foreground`** so CTA text
   stays legible on an arbitrary operator brand. A dark theme that hardcodes white CTA text would
   break the light-brand white-label case.
5. **The 4-field `BrandingPublic` shape + `GET /branding/current` / `GET /branding/logo` contract**
   (field names `brand_name`/`primary_hex`/`secondary_hex`/`logo_url`) and the multipart
   `PUT /api/v1/admin/tenant-config` body. Frontend types in `lib/branding-types.ts` /
   `branding-public.ts` are transcribed from these.
6. **`BrandLogo` renders the operator logo via `<img src=/branding/logo>`** (with the backend's
   nosniff/CSP headers). The premium "X" logo is the DEFAULT/unbranded asset only; an operator-
   uploaded logo must still override it. Do not hardcode the XPredict logo into markup in a way that
   defeats the upload path.
7. **Money discipline** (string end-to-end, no `parseFloat`/`Number()` for storage) in
   `admin-format.ts`, `kpi-card.tsx`, `volume-chart.tsx`, `recharge-form.tsx`, market/event forms.
8. **Settlement/CRUD logic** — action-gating booleans (`market-detail-actions.tsx`,
   `event-detail-admin-actions.tsx`), the two-prefix routing split (`/api/v1` CRUD vs bare `/admin`
   settlement/recharge/events), the edit-lock (423) handling, the Idempotency-Key on recharge, the
   `confirm:false→true` event two-step. These are behavior, not style.
9. **Data-table state machine** (`firstRender` skip, `resetToFirstPage`, manual pagination/sorting,
   `react-is` pin for Recharts). Restyle cells/chrome only.
10. **`destructive` button variant stays semantic red** — operators rely on it to distinguish
    irreversible settlement actions; do not fold it into the brand palette.

---

## 5. How much of the admin can adopt the premium design system

- **High reuse — adopt directly:** the admin and player share the SAME shadcn primitives
  (`button.tsx`, `card.tsx`, `dialog.tsx`, `select.tsx`, `table.tsx`, `input.tsx`, `form.tsx`,
  `badge.tsx`, `skeleton.tsx`, `tooltip.tsx`, `tabs.tsx`, sonner). Restyling these primitives once
  (dark surfaces, premium tokens) re-skins BOTH surfaces. The admin already inherits
  `bg-brand-primary` CTAs via `button.tsx` and has full `dark:` variants on its tables/badges/layout.
- **Admin is the FURTHEST behind on identity:** the shell wordmark is a static "XPredict Admin"
  string (no logo, no brand token), surfaces are `bg-zinc-50`/`bg-white`, and the dark variants exist
  but are never the default (the layout sets `bg-zinc-50 dark:bg-zinc-950` — it is NOT dark-first).
  Making the player dark-first should be mirrored in the admin shell.
- **Effort split:** ~70% of admin restyle is "restyle shared primitives + the page-chrome containers
  (`max-w-6xl px-6 py-12`, H1 sizes, table borders/headers, empty/error/loading states)" — all
  pure-presentational. ~30% is logic-coupled islands (forms, settlement dialogs, data-table state)
  where ONLY the inner markup/classes change and the behavior is untouchable.
- **Inconsistency to fix while restyling:** H1 sizing (`text-xl` list pages vs `text-3xl` dashboard/
  detail) and the static admin wordmark vs the player's brand-aware `BrandLogo` — the admin shell
  could adopt `BrandLogo` (or a brand-aware admin variant) to surface the operator's identity.
- **The branding form (`/admin/branding`) is the natural showcase** for the new design system: it is
  the operator's first touchpoint and currently the most generic. The live color swatches + logo
  preview are restyle-safe and ideal for a premium treatment.

---

## 6. Inventory quick-reference (file → one-liner)

- `app/admin/layout.tsx` — admin shell (static wordmark + nav + footer), not brand-aware.
- `components/admin/admin-nav.tsx` — hardcoded 6-link nav + Log out, active-state client component.
- `app/admin/page.tsx` + `kpi-dashboard.tsx` + `kpi-card.tsx` + `volume-chart.tsx` — KPI dashboard.
- `users-data-table.tsx` / `markets-data-table.tsx` / `audit-log-table.tsx` — server-driven tables.
- `user-detail-tabs.tsx` + `profile-tab/wallet-tab/bets-tab/recharge-form` — user detail island.
- `market-detail-actions.tsx` / `event-detail-admin-actions.tsx` — settlement action hosts.
- `resolve|force-settle|reverse-settlement|close-market|resolve-event|void-event|reverse-event|ban|unban` dialogs.
- `market-form.tsx` / `event-form.tsx` — create/edit forms (logic-coupled, criteria/edit locks).
- `branding-form.tsx` — operator branding editor (the white-label entry point).
- `lib/admin-api.ts` / `admin-markets-api.ts` / `admin-events-api.ts` / `branding-admin-api.ts` — Server Actions.
- `lib/admin-types.ts` / `admin-markets-types.ts` / `admin-events-types.ts` / `branding-types.ts` / `kpi-types.ts` — wire types.
- `lib/admin-format.ts` (money/date string formatters) / `admin-query.ts` (qs builders) / `brand-color.ts` (foreground).
- `lib/branding-public.ts` — public no-store branding fetch + `DEFAULT_BRANDING`.
- `app/layout.tsx` — player root: branding `<style>` injection + `BrandLogo`.
- `app/globals.css` — `:root` brand defaults + `@theme inline` Tailwind token mapping.
- `components/brand-logo.tsx` — operator logo `<img>` / wordmark fallback.
- backend: `branding/router.py` (public), `branding/admin_router.py` (admin PUT/GET), `branding/models.py`,
  `branding/repo.py`, `branding/schemas.py`; `admin/router.py`, `admin/kpi_router.py`,
  `admin/export_router.py`, `core/audit/router.py`.
