# Phase 12: Admin Market Operations UI & Player Resolution Display - Pattern Map

**Mapped:** 2026-06-03
**Files analyzed:** 23 new/modified files (8 backend, 15 frontend)
**Analogs found:** 23 / 23 (every new file is a clone of a named shipped file — this phase is clone-and-wire over Phases 4/5/7 backends + the 8/9/10 design system)

> **Scope source:** No CONTEXT.md exists for this phase. File list extracted from `12-RESEARCH.md` §Recommended Project Structure + §Code Examples, `12-UI-SPEC.md` §Component Inventory, and the ROADMAP Phase-12 success criteria. Every "new" file maps to a concrete analog cited `file:line` below.

---

## File Classification

### Backend (`backend/app/`)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `alembic/versions/0010_phase12_*.py` (NEW) | migration | batch DDL | `alembic/versions/0007_phase7_grace_period.py` | exact (add_column on `markets`) |
| `markets/models.py` (EDIT — Market: +5 cols) | model | — | `markets/models.py` Market (`volume:Mapped[Money]` L81; `resolved_at` L117) + `db/types.py` Money L20 | self (same file) |
| `markets/schemas.py` (EDIT — MarketRead +3, MarketCreate/Update +2) | schema | request-response | `markets/schemas.py` MarketRead L87-111 (`serialize_volume_decimal` L108) | self (same file) |
| `markets/router.py` (EDIT — get_market_public RESOLVED) | route | request-response | `markets/router.py` `get_market_public` L158-166 (guard L164) | self (same file) |
| `settlement/market_port.py` (EDIT — Protocol sig) | port (Protocol) | — | `settlement/market_port.py` `mark_resolved` L27-36 | self (same file) |
| `settlement/adapters.py` (EDIT — persist winner) | adapter | CRUD write | `settlement/adapters.py` `mark_resolved` L31-38 | self (same file) |
| `settlement/service.py` (EDIT — pass source) | service | event-driven (settle tx) | `settlement/service.py` `resolve_market` L84-92 + call site L220-222 + audit L227-240 | self (same file) |
| `bets/router.py` + `bets/service.py` + `bets/market_port.py` (EDIT — BET-06 per-market limit) | route/service/port | request-response | `bets/router.py` stake check L92-97; `bets/service.py` `place_bet` L80-88; `bets/market_port.py` MarketView L38-53 | self (same files) |

### Frontend (`frontend/src/`)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `lib/admin-markets-api.ts` (NEW) | service (`"use server"`) | request-response (Bearer-forward) | `lib/admin-api.ts` (whole; `adminApiFetch` L58-73, two-prefix evidence `rechargeWallet` L174-188) | exact |
| `lib/admin-markets-types.ts` (NEW) | types | — | `lib/admin-types.ts` (whole) | exact |
| `lib/__tests__/admin-markets-api.test.ts` (NEW — Wave 0) | test (node) | — | `lib/__tests__/admin-api.test.ts` (whole; prefix-contract guard L51-91) | exact |
| `app/admin/markets/page.tsx` (NEW) | page (Server Component) | request-response | `app/admin/users/page.tsx` (whole) | exact |
| `components/admin/markets-data-table.tsx` (NEW) | component (`"use client"`) | CRUD list (server-driven) | `components/admin/users-data-table.tsx` (whole) | exact |
| `components/admin/market-form.tsx` (NEW) | component (form) | CRUD create/edit | `components/admin/branding-form.tsx` (whole; RHF+zod+422 map L190-240) | role-match (form) |
| `components/admin/resolve-market-dialog.tsx` (NEW) | component (dialog) | command + confirm | `components/admin/ban-confirm-dialog.tsx` (whole; validate-then-submit L59-76) | exact |
| `components/admin/reverse-settlement-dialog.tsx` (NEW) | component (dialog) | command + confirm | `components/admin/ban-confirm-dialog.tsx` | exact |
| `components/admin/force-settle-dialog.tsx` (NEW) | component (dialog) | command + confirm | `components/admin/ban-confirm-dialog.tsx` | exact |
| `components/admin/market-status-badge.tsx` (NEW) | component (chip) | — | `components/admin/user-status-badge.tsx` (whole L10-32) | exact |
| `components/market-resolution-panel.tsx` (NEW) | component (player) | read-only display | `app/portfolio/page.tsx` PnL L86-100 + settled card L155-170; Card from `markets/[slug]/page.tsx` L193-205 | role-match (compose) |
| `components/admin/admin-nav.tsx` (EDIT — enable Markets) | component (nav) | — | self (L25-30 LINKS array; placeholder `<span>` L56-57) | self |
| `app/markets/[slug]/page.tsx` (EDIT — RESOLVED branch) | page (Server Component) | request-response | self (RIGHT column L192-206; cookie read L132-133) | self |
| `lib/api.ts` (EDIT — MarketDetail +resolution fields) | types/fetch | request-response | self (`MarketDetail` L52-54, `MarketItem` L16-31) | self |
| `lib/bet-schemas.ts` + `components/order-entry-form.tsx` (EDIT — BET-06 client) | schema/component | request-response | self (`BET_MIN/MAX_STAKE` L25-26, `BetSchema` L33-44; `expectedPayout` gate L91-103) | self |

---

## Pattern Assignments

### `lib/admin-markets-api.ts` (NEW — `"use server"` Bearer-forward data layer)

**Analog:** `frontend/src/lib/admin-api.ts`

**THE TWO-PREFIX LANDMINE (Pitfall 1) is proven by this same file:** `rechargeWallet` already targets a bare `/admin/...` path while every CRM call keeps `/api/v1/admin/...`. Clone that split exactly: **market CRUD → `/api/v1/admin/markets...`**, **settlement → bare `/admin/markets/{id}/resolve|reverse|force-settle`**.

**Bearer-forward core to clone verbatim** (`admin-api.ts:44-73`):
```typescript
"use server";
import { cookies } from "next/headers";

function getBackendUrl(): string {
  return process.env.BACKEND_URL || "http://localhost:8000";
}

async function bearerHeader(): Promise<Record<string, string>> {
  const store = await cookies();
  const token = store.get("admin_jwt")?.value;
  if (!token) {
    throw new Error("Not authenticated");
  }
  return { Authorization: `Bearer ${token}` };
}

export async function adminApiFetch<T = unknown>(
  path: string,
  init?: AdminFetchInit,
): Promise<T> {
  const auth = await bearerHeader();
  const res = await fetch(`${getBackendUrl()}${path}`, {
    method: init?.method,
    body: init?.body,
    headers: { ...(init?.headers ?? {}), ...auth },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  return res.json() as Promise<T>;
}
```

**The `/api/v1` CRM wrapper pattern** (`admin-api.ts:105-150`) — clone for `fetchMarkets`/`createMarket`/`updateMarket`/`closeMarket`:
```typescript
export async function fetchUsers(params: UserListParams): Promise<PaginatedResponse<UserListItem>> {
  const qs = buildUsersQuery(params);
  return adminApiFetch<PaginatedResponse<UserListItem>>(`/api/v1/admin/users${qs}`);
}
export async function banUser(id: string, reason: string): Promise<UserDetail> {
  return adminApiFetch<UserDetail>(`/api/v1/admin/users/${id}/ban`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
}
```

**The BARE-prefix wrapper pattern** (`admin-api.ts:174-188` `rechargeWallet`) — clone for `resolveMarket`/`reverseSettlement`/`forceSettle`:
```typescript
export async function rechargeWallet(userId, amount, reason, idempotencyKey): Promise<unknown> {
  return adminApiFetch(`/admin/wallets/${userId}/recharge`, {   // ← NO /api/v1
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ amount, reason }),
  });
}
```

**Backend request shapes (verified) the wrappers must send:**
- `createMarket` → `POST /api/v1/admin/markets`, body = `MarketCreate` (`markets/schemas.py:38-52`): `{question, resolution_criteria, deadline, initial_odds_yes?, category?}` (+ BET-06 `min_stake?`/`max_stake?` after the schema edit).
- `updateMarket` → `PATCH /api/v1/admin/markets/{id}`, body = `MarketUpdate` (`markets/schemas.py:55-70`): `{resolution_criteria?, deadline?, odds_yes?, category?}` (note field is `odds_yes`, NOT `initial_odds_yes`).
- `closeMarket` → `POST /api/v1/admin/markets/{id}/close` (no body — `router.py:122-136`).
- `resolveMarket` → `POST /admin/markets/{id}/resolve`, body = `ResolveMarketRequest` (`settlement/schemas.py:22-28`): `{winning_outcome_id, justification}` (`extra="forbid"`, `justification` `min_length=1`).
- `reverseSettlement` → `POST /admin/markets/{id}/reverse`, body = `ReverseSettlementRequest` (`settlement/schemas.py:61-66`): `{justification}` only.
- `forceSettle` → `POST /admin/markets/{id}/force-settle`, body = `ForceSettleRequest` (`settlement/schemas.py:41-47`): `{winning_outcome_id, justification}`.

**Adaptation:** `"use server"` allows only async exports — put all types in `admin-markets-types.ts` (see below). Reuse `buildQuery` from `lib/admin-query` for the list querystring (`source`, `status`, `category`, `page`, `page_size`).

---

### `lib/__tests__/admin-markets-api.test.ts` (NEW — Wave 0, THE most important new test)

**Analog:** `frontend/src/lib/__tests__/admin-api.test.ts` (whole file)

This is the regression guard for Pitfall 1. The analog already encodes the exact assertion shape — clone the hoisted `next/headers` mock + the global fetch spy, then assert each wrapper's URL.

**Mock + spy harness to clone verbatim** (`admin-api.test.ts:16-49`):
```typescript
const mocks = vi.hoisted(() => {
  const cookieStore = { get: vi.fn(() => ({ value: "test-admin-jwt" })), set: vi.fn(), delete: vi.fn() };
  const cookiesMock = vi.fn(async () => cookieStore);
  return { cookieStore, cookiesMock };
});
vi.mock("next/headers", () => ({ cookies: mocks.cookiesMock }));
// ...
fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
  new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } }),
);
process.env.BACKEND_URL = "http://backend.test";
```

**The two assertions the new test MUST encode** (mirror `admin-api.test.ts:51-90`):
```typescript
// CRUD keeps /api/v1
it("fetchMarkets -> /api/v1/admin/markets", async () => {
  await fetchMarkets({ page: 1, page_size: 20 });
  const [url] = fetchSpy.mock.calls[0] as [string, RequestInit?];
  expect(url).toContain("http://backend.test/api/v1/admin/markets");
});
// settlement is BARE — the regression: must NOT carry /api/v1
it("resolveMarket -> /admin/markets/{id}/resolve, NOT /api/v1", async () => {
  await resolveMarket("m-1", { winning_outcome_id: "o-1", justification: "x" });
  const [url] = fetchSpy.mock.calls[0] as [string, RequestInit?];
  expect(url).toBe("http://backend.test/admin/markets/m-1/resolve");
  expect(url).not.toContain("/api/v1/admin/markets");
});
```

---

### `components/admin/markets-data-table.tsx` (NEW — TanStack v8 server-driven list)

**Analog:** `frontend/src/components/admin/users-data-table.tsx` (whole file — 387 lines)

Clone the entire file. The state machine (`manualPagination`/`manualSorting`, `firstRender` skip, `resetToFirstPage`, loading/error/empty branches, rows-as-links) transfers verbatim.

**The fetch-effect + skip-first-render pattern** (`users-data-table.tsx:170-206`) — keep verbatim, swap `fetchUsers`→`fetchMarkets`:
```typescript
const firstRender = React.useRef(true);
React.useEffect(() => {
  if (firstRender.current) { firstRender.current = false; return; }
  let cancelled = false;
  setLoading(true); setError(false);
  fetchUsers({ ...currentFilters, page, page_size: PAGE_SIZE })
    .then((res) => { if (!cancelled) setData(res); })
    .catch(() => { if (!cancelled) setError(true); })
    .finally(() => { if (!cancelled) setLoading(false); });
  return () => { cancelled = true; };
}, [currentFilters, page]);
```

**The filter bar to SWAP** (`users-data-table.tsx:229-268`): replace the single status `<Select>` (L239-257) with **three** Selects — source (`HOUSE`/`POLYMARKET`), status (the 5 `MarketStatus`), category. Keep the `flex flex-wrap items-end gap-4` wrapper and the `resetToFirstPage()` on every change. Drop `AdminSearchInput`/`DateRangeFilter`/`ExportCsvButton` unless the list needs them (RESEARCH lists no search/export for markets).

**The rows-as-links + a11y block** (`users-data-table.tsx:345-360`) — keep verbatim, swap the target:
```typescript
<TableRow role="link" tabIndex={0} aria-label={`View market ${row.original.question}`}
  className="group cursor-pointer"
  onClick={() => router.push(`/admin/markets/${row.original.id}`)}
  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); router.push(`/admin/markets/${row.original.id}`); } }}>
```

**Columns to define** (swap the `columns` array `users-data-table.tsx:70-143`): question / source badge (`SourceBadge`) / status badge (`MarketStatusBadge` — see below) / category / deadline (`formatDate`) / `bet_count` / created_at (`formatDate`) / "View". Default sort `[{ id: "created_at", desc: true }]` (L165-167); `PAGE_SIZE = 20`.

**Backend contract:** `fetchMarkets` returns `PaginatedResponse<MarketListItem>` from `GET /api/v1/admin/markets` (`router.py:52-77`). `MarketListItem` (`markets/schemas.py:114-149`) carries `id, question, slug, category, source, status, deadline, bet_count, created_at, source_url, outcomes`. Backend filters are `source`/`status`/`category` (typed `MarketSourceEnum`/`MarketStatus` Query params, `router.py:58-60`).

**Loading/empty/error copy is already in the analog** — mirror verbatim (`users-data-table.tsx:309-343`): skeleton 5 rows `h-4 w-full` `aria-busy`; "Failed to load data" + "Something went wrong while loading this page. Please try again."; "No users found" → "No markets found" + "No markets match your current filters. Try adjusting the search or filter criteria."

---

### `components/admin/market-status-badge.tsx` (NEW — status chip)

**Analog:** `frontend/src/components/admin/user-status-badge.tsx` (whole, L10-32)

**The chip primitive to clone** (`user-status-badge.tsx:18-31`):
```tsx
<span
  aria-label={`Status: ${label}`}
  className={cn(
    "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
    colorClasses,   // ← swap the binary active/banned for a 5-way status map
    className,
  )}
>
  {label}
</span>
```

**Adaptation:** the analog is binary (active emerald / banned red). Replace with the 5-state map from UI-SPEC §Status badge palette: `OPEN`→`bg-emerald-100 text-emerald-700`, `CLOSED`→`bg-amber-100 text-amber-700`, `RESOLVED`→`bg-zinc-900 text-zinc-50`, `CANCELLED`→`bg-red-100 text-red-700`, `DRAFT`→`bg-zinc-100 text-zinc-600` (+ the dark-mode variants tabled in UI-SPEC). Keep the `px-2.5 py-0.5 text-xs font-semibold` inset verbatim (locked inherited exception) and the `aria-label="Status: {state}"`.

---

### `components/admin/market-form.tsx` (NEW — RHF + zod create/edit form)

**Analog:** `frontend/src/components/admin/branding-form.tsx` (whole, 321 lines)

**The form scaffold** (`branding-form.tsx:24-31, 150-158, 242-251`) — clone the `"use client"` + `useForm`+`zodResolver` + `<Form {...form}>` + `max-w-lg flex-col gap-4` layout + `Loader2` spinner:
```typescript
const form = useForm<MarketFormValues>({ resolver: zodResolver(MarketSchema), defaultValues, mode: "onSubmit" });
// ...
<form onSubmit={(e) => { e.preventDefault(); void onSubmit(e); }} className="flex max-w-lg flex-col gap-4" noValidate>
```

**The FormField idiom to repeat per field** (`branding-form.tsx:252-264`):
```tsx
<FormField control={form.control} name="question" render={({ field }) => (
  <FormItem>
    <FormLabel>Question</FormLabel>
    <FormControl><Input type="text" {...field} /></FormControl>
    <FormMessage />
  </FormItem>
)} />
```

**The 422 → inline FormMessage mapping** (`branding-form.tsx:205-236`) — this is the load-bearing pattern; clone the status branching:
```typescript
} catch (err) {
  const { status, fieldErrors } = parseBrandingApiError(err);
  if (status === 401 || status === 403) {
    toast.error("Your session expired. Please sign in again.");
  } else if (status === 422) {
    for (const [field, message] of Object.entries(fieldErrors)) {
      form.setError(field as keyof MarketFormValues, { type: "server", message });
    }
  } else {
    toast.error("Couldn't save changes. Please try again.");
  }
}
```

**zod schema mirrors the server (UX-only):** create-mode mirrors `MarketCreate` (`markets/schemas.py:38-52`) — `question` 1..500, `resolution_criteria` 1..2000, `deadline` future datetime, `initial_odds_yes` `(0,1)` default `0.5`, `category` optional ≤100. Edit-mode mirrors `MarketUpdate` (`markets/schemas.py:55-70`) — note the field is **`odds_yes`** not `initial_odds_yes`. Submit success → `toast.success("Market created." | "Market updated.")` (UI-SPEC §Toast).

**ADM-07 (criteria lock):** DISABLE the `resolution_criteria` field when `bet_count > 0` and show the helper "Resolution criteria are locked once a market has bets." (the backend returns 423 CRITERIA_LOCKED authoritatively). Odds + deadline stay editable with bets (documented Phase-4 deviation).

**BET-06 fields (A-STAKE-FIELDS):** two optional money `Input`s **Min stake** / **Max stake** with `inputMode="decimal"` under the odds field; zod cross-field `min ≤ max`; blank = platform default; values stay money STRINGS (never `parseFloat` for storage — mirror the money discipline in `branding-form` and `kpi-card.tsx:37-51`).

---

### `components/admin/resolve-market-dialog.tsx` + `reverse-settlement-dialog.tsx` + `force-settle-dialog.tsx` (NEW — two-step confirm dialogs)

**Analog:** `frontend/src/components/admin/ban-confirm-dialog.tsx` (whole, 133 lines)

**The validate-then-submit core to clone verbatim** (`ban-confirm-dialog.tsx:59-76`) — mandatory-justification gate + stays-open-during-submit + toast:
```typescript
async function handleConfirm() {
  if (reason.trim().length < 1) {
    setValidationError("A reason is required to ban a user");   // ← swap copy: "A justification is required."
    return;
  }
  setValidationError(null);
  setSubmitting(true);
  try {
    const updated = await banUser(userId, reason.trim());        // ← swap to resolveMarket/reverseSettlement/forceSettle
    toast.success("User has been banned");                       // ← swap: "Market resolved." etc.
    onBanned(updated);
    onOpenChange(false);
  } catch {
    toast.error("Failed to ban user. Please try again.");        // ← swap failure copy
  } finally {
    setSubmitting(false);
  }
}
```

**The dialog shell + close-guard + reset-on-open** (`ban-confirm-dialog.tsx:50-57, 78-131`):
```tsx
React.useEffect(() => { if (open) { setReason(""); setValidationError(null); setSubmitting(false); } }, [open]);
// ...
<Dialog open={open} onOpenChange={(o) => !submitting && onOpenChange(o)}>   // ← blocks close while submitting (a11y + double-click guard)
  <DialogContent>
    <DialogHeader><DialogTitle>Ban user</DialogTitle><DialogDescription>...</DialogDescription></DialogHeader>
    <div className="flex flex-col gap-2">
      <Label htmlFor={reasonId}>Reason (required)</Label>
      <Textarea id={reasonId} value={reason} onChange={...} disabled={submitting} aria-invalid={!!validationError} />
      {validationError && <p role="alert" className="text-sm font-medium text-red-500">{validationError}</p>}
    </div>
    <DialogFooter>
      <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>Cancel</Button>
      <Button variant="destructive" onClick={() => void handleConfirm()} disabled={submitting}>
        {submitting && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
        Confirm ban   {/* ← "Confirm resolve" | "Confirm reversal" | "Confirm force-settle" */}
      </Button>
    </DialogFooter>
  </DialogContent>
</Dialog>
```

**Per-dialog adaptations:**
- **resolve-market-dialog** (STL-02/ADM-05): add a YES/NO outcome `<Select>` ABOVE the justification `Textarea` (the only structural addition — feed it `market.outcomes`); title "Resolve market"; calls `resolveMarket(id, {winning_outcome_id, justification})` → **bare** `/admin/markets/{id}/resolve`.
- **force-settle-dialog** (ADM-06): same outcome `Select` + justification; title "Force-settle market"; calls `forceSettle(id, {winning_outcome_id, justification})`.
- **reverse-settlement-dialog** (STL-07): justification ONLY (no outcome Select); title "Reverse settlement"; calls `reverseSettlement(id, {justification})`. Body copy MUST use the §Reverse copy guard ("does not re-open the market for a clean re-resolution" — Pitfall 5).

The two-step requirement is satisfied structurally: button reveals dialog (step 1: propose + justify) → destructive Confirm submits (step 2).

---

### `components/market-resolution-panel.tsx` (NEW — player RESOLVED display, STL-06)

**Analog (compose, not single-file clone):** `app/portfolio/page.tsx` (PnL + settled card) + the order-panel Card from `app/markets/[slug]/page.tsx:193-205`.

**The signed-P&L sign-coloring component to clone verbatim** (`portfolio/page.tsx:86-100`) — note LOSS is `zinc-700`, NOT red (A-LOSS-NEUTRAL):
```tsx
function PnL({ value }: { value: string }) {
  const negative = value.trim().startsWith("-");
  return (
    <span className={negative
      ? "text-sm font-medium text-zinc-700 dark:text-zinc-300"
      : "text-sm font-medium text-emerald-600"}>
      {negative ? "" : "+"}{value} {CURRENCY}
    </span>
  );
}
```

**The won/lost settled-card row to mirror** (`portfolio/page.tsx:155-170`):
```tsx
<CardTitle className="text-base font-medium">
  {p.won ? "Won" : "Lost"} — payout {p.payout} {CURRENCY}
</CardTitle>
// ...
<span className="min-w-0 text-sm text-zinc-500">Realized P&amp;L</span>
<PnL value={p.realized_pnl} />
```

**The Card wrapper to match the slot it replaces** (`markets/[slug]/page.tsx:193-205`): `<Card className="lg:sticky lg:top-8">` + `<CardHeader><CardTitle className="text-lg font-semibold">Resolution</CardTitle></CardHeader>` + `<CardContent className="flex flex-col gap-4">`.

**Panel rows (UI-SPEC Surface 1):** winning outcome label (emerald chip if the player won, else neutral); resolution source — derive from token: `"POLYMARKET_UMA"`→"Polymarket UMA" (+ `SourceBadge` source_url), `"HOUSE"`→"Operator: {display_name}"; `formatDate(resolved_at)` prefixed "Settled "; justification as ESCAPED React text (NEVER `dangerouslySetInnerHTML`); `Separator`; then the player's own result (Won/Lost + payout + PnL) when logged-in-and-bet, "You didn't bet on this market." when logged-in-no-bet, omit entirely when logged out.

**Adaptation / open design choice (RESEARCH A2 / Pitfall 6):** the panel needs the resolver display name at read time but the public read has no admin join — planner must confirm whether the backend supplies a `resolution_source` token + a `display_name` snapshot on `MarketRead`, or token-only (panel falls back to "Operator" without a name). Write the copy defensively either way.

---

### `app/admin/markets/page.tsx` (NEW — Server Component list shell)

**Analog:** `frontend/src/app/admin/users/page.tsx` (whole) + `app/admin/branding/page.tsx` (degrade pattern).

**Clone verbatim, swap fetch + table + add a Create button** (`admin/users/page.tsx:16-37`):
```tsx
export const dynamic = "force-dynamic";
export default async function AdminMarketsPage() {
  let initialData: PaginatedResponse<MarketListItem>;
  try {
    initialData = await fetchMarkets({ page: 1, page_size: 20, sort_by: "created_at", sort_order: "desc" });
  } catch {
    initialData = { items: [], total: 0, page: 1, page_size: 20, pages: 1 };
  }
  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <h1 className="mb-8 text-xl font-semibold tracking-tight">Markets</h1>
      {/* + top-right "Create market" Button → opens create form (new/page.tsx or dialog) */}
      <MarketsDataTable initialData={initialData} />
    </div>
  );
}
```
**Adaptation:** add a `[id]/page.tsx` detail page (Open Q1 recommended default) hosting the edit form + the three settlement action buttons gated by status (OPEN/CLOSED house→Resolve; OPEN/CLOSED Polymarket→Force-settle; RESOLVED→Reverse) — mirrors the shipped `/admin/users/[id]` detail-page-hosts-actions convention.

---

### `app/markets/[slug]/page.tsx` (EDIT — add RESOLVED branch)

**Analog:** self.

**The exact insertion point — RIGHT column** (`markets/[slug]/page.tsx:191-206`). When `market.status === "RESOLVED"`, render `<MarketResolutionPanel ... />` in place of the `OrderEntryForm` Card; otherwise leave the Card unchanged. The LEFT column (header, live odds, criteria, chart, activity) stays untouched. Add a `MarketStatusBadge`/RESOLVED chip next to `<SourceBadge>` in the header (L138-143).

**The player-payout fetch to add** (mirror `portfolio/page.tsx:65-83` + the cookie read already present at `markets/[slug]/page.tsx:132-133`):
```typescript
const store = await cookies();
const session = store.get("xpredict_session")?.value;
let myResult: SettledPosition | null = null;
if (session && market.status === "RESOLVED") {
  const res = await fetch(`${apiBase()}/bets/me/portfolio`, {
    headers: { Cookie: `xpredict_session=${session}` }, cache: "no-store",
  });
  if (res.ok) {
    const data = await res.json();
    myResult = (data.settled ?? []).find((p: SettledPosition) => p.market_id === market.id) ?? null;
  }
}
```
`SettledPosition` shape is in `portfolio/page.tsx:43-52` (`{bet_id, market_id, outcome_id, stake, odds_at_placement, won, payout, realized_pnl}`). NEVER query another user's payout (self-scoped by the player's own cookie).

---

### `lib/api.ts` (EDIT — extend MarketDetail with resolution fields)

**Analog:** self.

**The gap:** `MarketDetail` (`lib/api.ts:52-54`) extends `MarketItem` (L16-31) and currently has NEITHER the resolution fields NOR an explicit `volume_24hr` mismatch issue. For STL-06 the panel needs them — add to `MarketDetail` (or `MarketItem`):
```typescript
export interface MarketDetail extends MarketItem {
  resolution_criteria: string;
  winning_outcome_id: string | null;       // NEW — STL-06
  resolution_source: string | null;        // NEW — "HOUSE" | "POLYMARKET_UMA"
  resolution_justification: string | null; // NEW
  resolved_at: string | null;              // NEW (already on backend MarketRead L105)
}
```
`fetchMarket` (L131-145) already throws `MarketNotFound` on 404 — once the backend stops 404ing RESOLVED, a resolved slug returns 200 and this typed shape carries the panel data.

---

### `components/order-entry-form.tsx` + `lib/bet-schemas.ts` (EDIT — BET-06 client mirror)

**Analog:** self.

**The client min/max gate to extend** (`bet-schemas.ts:25-44`) — today hardcoded global constants:
```typescript
export const BET_MIN_STAKE = 1;       // mirror of config BET_MIN_STAKE
export const BET_MAX_STAKE = 100000;  // mirror of config BET_MAX_STAKE
export const BetSchema = z.object({
  outcome: z.enum(["YES", "NO"]),
  stake: z.string().min(1, "Enter a stake")
    .refine((v) => /^\d+(\.\d+)?$/.test(v.trim()), { message: "Enter a valid amount" })
    .refine((v) => Number(v) >= BET_MIN_STAKE && Number(v) <= BET_MAX_STAKE, {
      message: `Stake must be between ${BET_MIN_STAKE} and ${BET_MAX_STAKE} PLAY_USD.`,
    }),
});
```
**Adaptation:** prefer the market's `min_stake`/`max_stake` (from the extended market read) when present, else fall back to the globals. Because `BetSchema` is module-level static, the per-market bounds likely need to become a schema factory `makeBetSchema(min, max)` OR an extra `.refine` in `order-entry-form.tsx` reading the market props. The out-of-range message stays `"Stake must be between {min} and {max} PLAY_USD."` (UI-SPEC).

**The `expectedPayout` "—" gate to keep in sync** (`order-entry-form.tsx:91-103`): it bounds on the SAME min/max so the preview and submit agree — update it to use the per-market bounds too. The `BetConfirmDialog` flow (L295-304) and the `role="alert"` bet-error region (L255-272) are unchanged; a 422 from `/bets` maps to that existing inline region.

---

### `alembic/versions/0010_phase12_*.py` (NEW — add 5 columns to markets)

**Analog:** `backend/alembic/versions/0007_phase7_grace_period.py` (the add_column template).

**Confirmed single head:** the full revision sweep shows a linear chain `0001→0002→0003→{0004_wallet, 0004_polymarket}→0006_merge→0007→0008→0009`. **`0009_phase10_tenant_config` is the unique current head** (no revision has it as `down_revision`). So `down_revision = "0009_phase10_tenant_config"` is correct; `0010` is the right next number.

**The add_column shape to clone** (`0007:26-34`):
```python
revision: str = "0010_phase12_resolution_and_stake_limits"
down_revision: str | None = "0009_phase10_tenant_config"

def upgrade() -> None:
    op.add_column("markets", sa.Column("winning_outcome_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("markets", sa.Column("resolution_source", sa.String(40), nullable=True))
    op.add_column("markets", sa.Column("resolution_justification", sa.Text, nullable=True))
    op.add_column("markets", sa.Column("min_stake", sa.Numeric(18, 4), nullable=True))   # BET-06
    op.add_column("markets", sa.Column("max_stake", sa.Numeric(18, 4), nullable=True))   # BET-06
    # OPTIONAL idempotent backfill of winning_outcome_id from audit_log for pre-Phase-12 RESOLVED markets (A3 — planner decides)

def downgrade() -> None:
    for col in ("max_stake", "min_stake", "resolution_justification", "resolution_source", "winning_outcome_id"):
        op.drop_column("markets", col)
```
**Note:** `0007` imports `sqlalchemy as sa`; for `postgresql.UUID` add `from sqlalchemy.dialects import postgresql` (other migrations already use it).

---

### `markets/models.py` (EDIT — Market gains 5 columns)

**Analog:** self — the existing `Market` columns ARE the template.

**Existing money column pattern** (`models.py:81-84`): `volume: Mapped[Money] = mapped_column(server_default="0", default=Decimal("0"))`.
**Existing nullable-timestamp pattern** (`models.py:117-120`): `resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)`.

**CRITICAL money-lint constraint (`db/types.py:1-21`):** `Money = Annotated[Decimal, mapped_column(Numeric(18, 4), nullable=False)]` — it is **NOT-NULL**. The new `min_stake`/`max_stake` are NULLABLE (NULL = use global default), so they MUST use the documented nullable-money exception (`db/types.py:7-9`), NOT `Mapped[Money]`:
```python
# NULLABLE money — the documented exception so scripts/lint_money_columns.py stays green:
min_stake: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
max_stake: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
# Resolution columns:
winning_outcome_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
resolution_source: Mapped[str | None] = mapped_column(String(40), nullable=True)
resolution_justification: Mapped[str | None] = mapped_column(Text, nullable=True)
```
(`Decimal`, `UUID`, `String`, `Text` are all already imported at the top of the file.)

---

### `markets/schemas.py` (EDIT — MarketRead +3 resolution fields, +2 stake fields)

**Analog:** self — `MarketRead` (`schemas.py:87-111`) is the template.

**The money-string serializer to mirror for new money fields** (`schemas.py:108-111`):
```python
@field_serializer("volume", "volume_24hr")
@classmethod
def serialize_volume_decimal(cls, v: Decimal) -> str:
    return str(v)
```
**Adaptation:** add `winning_outcome_id: UUID | None`, `resolution_source: str | None`, `resolution_justification: str | None` to `MarketRead` (resolved_at already present L105). Add `min_stake: Decimal | None` / `max_stake: Decimal | None` to `MarketRead` AND `MarketCreate` (L38-52) / `MarketUpdate` (L55-70) for BET-06 — extend the `field_serializer` to include the nullable stake fields (guard `None`: `str(v) if v is not None else None`).

---

### `markets/router.py` (EDIT — relax the get_market_public 404 guard)

**Analog:** self.

**The exact guard to change** (`router.py:158-166`):
```python
@public_market_router.get("/{slug}", response_model=MarketRead)
async def get_market_public(slug, session):
    market = await MarketService.get_market_by_slug(session, slug)
    if not market or market.status not in (MarketStatus.OPEN.value, MarketStatus.CLOSED.value):
        raise HTTPException(status_code=404, detail="Market not found")
    return MarketRead.model_validate(market)
```
**Adaptation:** add `MarketStatus.RESOLVED.value` to the allowed tuple. RESEARCH (Pitfall 3) notes the same guard exists in `MarketService.price_history` and `recent_activity` — surfacing those for RESOLVED is recommended (A5) so the chart keeps its pre-resolution history, but only `get_market_public` is strictly required for STL-06.

---

### `settlement/market_port.py` + `settlement/adapters.py` + `settlement/service.py` (EDIT — STL-06 persist-winner, ATOMIC across all three)

**This is the single highest-risk change (Pitfall 2). The Protocol signature ripples to the real adapter, the service call site, AND 6 test fakes — do it as ONE atomic task.**

**Protocol — current signature to extend** (`market_port.py:27-29`):
```python
async def mark_resolved(self, session: AsyncSession, *, market_id: UUID, winning_outcome_id: UUID) -> None: ...
```
**Real adapter — the winner-discard bug to fix** (`adapters.py:31-38`) — currently sets ONLY status + resolved_at:
```python
async def mark_resolved(self, session, *, market_id, winning_outcome_id) -> None:
    market = await session.get(Market, market_id)
    if market is None: raise NoResultFound(f"no market {market_id}")
    market.status = MarketStatus.RESOLVED.value
    market.resolved_at = datetime.now(UTC)
    # MISSING: winning_outcome_id / resolution_source / resolution_justification never written
```
**Service call site to update** (`service.py:217-222`) + the audit row already records the winner (`service.py:227-240`, so the audit trail is unchanged):
```python
await market_resolver.mark_resolved(session, market_id=market_id, winning_outcome_id=winning_outcome_id)
```
**Service signature for deriving `resolution_source`** (`service.py:83-92`): `resolve_market(..., justification: str, actor_user_id: UUID | None = None)`. Derive source from `actor_user_id`: `None`→`"POLYMARKET_UMA"` (auto path), else `"HOUSE"` (admin). Pass `resolution_source` + `justification` through to `mark_resolved`.

**The 6 fakes that MUST change in lockstep** (mypy/runtime conformance will flag each — that is the lockstep signal):
1. `tests/settlement/test_settlement_router.py:84` — `FakeMarketResolver.mark_resolved` (excerpt below)
2. `tests/settlement/test_resolve_market.py:99` and `:112` (two classes)
3. `tests/settlement/test_force_settle.py:57`
4. `tests/settlement/test_market_resolve_port.py:19`
5. `tests/admin/test_kpi.py:96`

**The fake signature to update (all 6 follow this shape)** (`test_settlement_router.py:79-88`):
```python
class FakeMarketResolver:
    def __init__(self) -> None:
        self.resolved: list[tuple[UUID, UUID]] = []
        self.reopened: list[UUID] = []
    async def mark_resolved(self, session, *, market_id: UUID, winning_outcome_id: UUID) -> None:  # ← add resolution_source, justification
        self.resolved.append((market_id, winning_outcome_id))
    async def mark_unresolved(self, session, *, market_id: UUID) -> None:
        self.reopened.append(market_id)
```

> **DISCREPANCY vs RESEARCH:** RESEARCH §Pitfall 2 names 4 fakes; the actual grep finds **6** `mark_resolved` definitions across 5 test files (`test_resolve_market.py` has two). The planner's atomic task must update all 6.

---

### `bets/router.py` + `bets/service.py` + `bets/market_port.py` (EDIT — BET-06 per-market enforcement)

**Analog:** self.

**The current global-only server check to augment** (`bets/router.py:91-97`):
```python
settings = get_settings()
if not (settings.BET_MIN_STAKE <= body.stake <= settings.BET_MAX_STAKE):
    raise HTTPException(status_code=422, detail=f"Stake must be between {settings.BET_MIN_STAKE} and {settings.BET_MAX_STAKE}.")
```
**The global default source** (`core/config.py:79-81`): `BET_MIN_STAKE = Decimal("1.0000")`, `BET_MAX_STAKE = Decimal("100000.0000")` — these stay as the fallback (Runtime State Inventory: NOT removed).

**The placement decision (RESEARCH A4):** the router checks BEFORE calling the service and does NOT have the market loaded; only `BetService.place_bet` fetches it (via the port, `service.py:80-88`). Cleanest is to move the per-market check INTO `place_bet` right after `market.is_open(...)` validation (`service.py:84-88`), preferring `market.min_stake`/`max_stake` and falling back to the config globals.

**The port that must carry the limits** (`bets/market_port.py:38-53`) — `MarketView` is a frozen dataclass; add `min_stake`/`max_stake` (nullable `Decimal | None`):
```python
@dataclass(frozen=True, slots=True)
class MarketView:
    id: UUID
    status: str
    deadline: datetime
    outcomes: tuple[OutcomeView, ...]
    # NEW (BET-06): per-market stake bounds; None => use the global config default
    min_stake: Decimal | None = None
    max_stake: Decimal | None = None
```
The concrete `HouseMarketReadAdapter` (`app/bets/adapters.py`) and any test stub building a `MarketView` must populate the two new fields.

---

## Shared Patterns

### Authentication (admin Bearer-forward)
**Source:** `lib/admin-api.ts:44-73` (`bearerHeader` + `adminApiFetch`).
**Apply to:** `admin-markets-api.ts` (all CRUD + settlement wrappers). The `admin_jwt` HttpOnly cookie is read server-side and forwarded as `Authorization: Bearer`; the token never reaches client JS. Backend gate is `current_active_admin` on every admin route (`markets/router.py:43`, `settlement/router.py:63`). Player payout read forwards the `xpredint_session` cookie instead (`portfolio/page.tsx:68-73`).

### Money discipline (string end-to-end)
**Source:** `kpi-card.tsx:37-51` (`formatMoney`, pure string ops), `portfolio/page.tsx:86-100` (`PnL` reads sign from string), `markets/schemas.py:108-111` (backend `Decimal→str` serializer), `db/types.py:20` (`Money = Numeric(18,4)`).
**Apply to:** every new money surface — the BET-06 stake-limit columns (nullable-money exception, NOT `Mapped[Money]`), the `MarketRead` stake fields (string serializer), the resolution panel payout, the market-form stake inputs. NEVER `parseFloat` for storage.

### Two-step confirm + mandatory justification
**Source:** `ban-confirm-dialog.tsx:59-76` (validate-then-submit) + `:79` (close-guard during submit).
**Apply to:** all three settlement dialogs. Backend enforces `justification` `min_length=1` (`settlement/schemas.py:28,47,66`); the dialog blocks empty client-side too. `role="alert"` + `aria-invalid` on the error (a11y contract).

### RHF + zod + 422-mapping form
**Source:** `branding-form.tsx:150-158` (useForm), `:190-240` (submit + status-branched error map), `:242-251` (`max-w-lg flex-col gap-4` layout).
**Apply to:** `market-form.tsx`. zod mirrors the server contract for UX only; 422 maps server field errors to inline `FormMessage`; 401/403 → "Your session expired" toast.

### TanStack v8 server-driven table
**Source:** `users-data-table.tsx` (whole) — `manualPagination`/`manualSorting`, `firstRender` skip (`:170-206`), `resetToFirstPage` on filter change, rows-as-links a11y (`:345-360`), skeleton/empty/error states (`:309-343`).
**Apply to:** `markets-data-table.tsx`.

### Server Component page shell (admin)
**Source:** `admin/users/page.tsx:16-37` (`dynamic="force-dynamic"`, initial fetch, degrade-to-empty on catch, `mx-auto max-w-6xl px-6 py-12`).
**Apply to:** `app/admin/markets/page.tsx` (+ `[id]/page.tsx`).

### `"use server"` types split
**Source:** `lib/admin-types.ts` (whole) — a `"use server"` module exports only async fns, so all shared interfaces live in a sibling types file.
**Apply to:** `admin-markets-types.ts` (define `MarketListItem`, `MarketDetail`, request bodies, `PaginatedResponse<T>`, filter params — transcribe verbatim from the verified backend `markets/schemas.py` + `settlement/schemas.py`).

---

## No Analog Found

None. Every new/modified file maps to a concrete shipped analog (this is by design — RESEARCH §Don't Hand-Roll: "almost every 'new' file is a clone of a named existing file with the endpoint and fields swapped"). The only genuinely-new LOGIC (not a clone) is:
- the `0010` migration body (templated on `0007`),
- the `mark_resolved` 3-field persist (a 3-line addition inside the existing adapter),
- the per-market stake check (a fallback comparison inside the existing `place_bet`).

The one component without a single-file clone is `market-resolution-panel.tsx`, which COMPOSES three existing pieces (portfolio `PnL`, settled-card layout, the detail-page Card) rather than cloning one file — classified role-match above.

---

## Metadata

**Analog search scope:** `frontend/src/{lib,components/admin,components,app/admin,app/markets,app/portfolio}`, `backend/app/{markets,settlement,bets,core,db,auth}`, `backend/alembic/versions`, `backend/tests/settlement`, `backend/tests/admin`.
**Files scanned:** 24 source files read in full or targeted-section + 1 full alembic revision sweep + 1 test grep for `mark_resolved` signatures.
**Key verifications beyond RESEARCH:**
- Alembic head = `0009_phase10_tenant_config` (unique; full sweep confirms no fork) → `0010` correct.
- `mark_resolved` fakes = **6** definitions across 5 test files (RESEARCH said 4) — full list in the STL-06 section.
- `Money` annotation is NOT-NULL → BET-06 nullable columns MUST use the `Mapped[Decimal | None] = mapped_column(Numeric(18,4), nullable=True)` exception, not `Mapped[Money]` (else the migration shape and the lint diverge).
- `MarketUpdate` odds field is `odds_yes` (not `initial_odds_yes` as in `MarketCreate`) — the edit form/wrapper must use the right name.
- `lib/api.ts` `MarketDetail` currently lacks the resolution fields — must be extended for the panel to type-check.
**Pattern extraction date:** 2026-06-03

---

## PATTERN MAPPING COMPLETE

**Phase:** 12 - Admin Market Operations UI & Player Resolution Display
**Files classified:** 23 (8 backend, 15 frontend)
**Analogs found:** 23 / 23

### Coverage
- Files with exact analog: 14 (all the clone targets — table, dialogs, api layer, types, test, page shell, status badge)
- Files with role-match / self-edit analog: 9 (market-form role-match; market-resolution-panel compose; the 8 same-file backend + 3 same-file frontend edits)
- Files with no analog: 0

### Key Patterns Identified
- The two-prefix landmine is FIRST-PARTY proven in `admin-api.ts` itself (`rechargeWallet` bare-prefix vs CRM `/api/v1`) — clone that split for the settlement vs CRUD wrappers; the Wave-0 URL-contract test (`admin-api.test.ts`) is the guard to clone.
- STL-06 is one atomic backend task: Protocol (`market_port.py:27`) + real adapter (`adapters.py:31-38`) + service call site (`service.py:220`) + 6 test fakes change in lockstep; the audit row already records the winner so only a denormalized column projection is added.
- Money is string end-to-end (`formatMoney`/`Decimal→str`); the new nullable stake columns are the documented `nullable=True` exception to `Mapped[Money]` — using `Mapped[Money]` would break the lint/migration.
- Every admin UI surface is a verbatim clone of a Phase 8/9/10 file (`users-data-table`, `branding-form`, `ban-confirm-dialog`, `user-status-badge`, `admin/users/page`) with endpoint + fields swapped.

### File Created
`C:\Users\pobom\xpredict\.planning\phases\12-admin-market-operations-ui-and-player-resolution-display\12-PATTERNS.md`

### Ready for Planning
Pattern mapping complete. Every new/modified file has a cited analog (`file:line`) with the concrete excerpt and the specific adaptation. The planner can write deep tasks with accurate `read_first` targets, real signatures, and the exact lockstep edit set for the STL-06 ripple.
