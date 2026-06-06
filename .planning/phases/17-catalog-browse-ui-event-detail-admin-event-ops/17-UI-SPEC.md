---
phase: 17
slug: catalog-browse-ui-event-detail-admin-event-ops
status: approved
shadcn_initialized: true
preset: "shadcn/ui new-york (vendored — no components.json; primitives live in src/components/ui)"
created: 2026-06-06
---

# Phase 17 — UI Design Contract

> Visual + interaction contract for the v1.2 catalog frontend (browse · multi-outcome event card · event detail · admin event ops). XPredict shipped a mature design system across Phases 8/9/10/12; **this phase invents no design language** — it EXTRACTS the locked system and specifies how the Phase-17 surfaces conform. Every "new" component is a clone of a NAMED existing file with the data source swapped. Treat the inherited tokens (spacing 4px scale, the 7-size/2-weight type system, the neutral-zinc + single `--brand-*` accent palette) as **LOCKED** — see `milestones/v1.0-phases/12-admin-market-operations-ui-and-player-resolution-display/12-UI-SPEC.md` for the full inventory; this spec does not re-declare them.
>
> **No CONTEXT round-trip needed** beyond `17-CONTEXT.md` (smart-discuss). Genuinely-undecided NET-NEW choices carry a recommended default inline.

---

## Design System (inherited — LOCKED)

| Property | Value | Source |
|----------|-------|--------|
| Tool | shadcn/ui (vendored — no `components.json`) | `src/components/ui/*` (button, card, dialog, form, input, select, textarea, badge, label, skeleton, tabs, sonner, separator) |
| Preset | "new-york", neutral **zinc** | `button.tsx` |
| Forms | `react-hook-form` + `@hookform/resolvers` + `zod` (UX mirror; FastAPI is authoritative) | `market-form.tsx`, `order-entry-form.tsx` |
| Dynamic field arrays | `react-hook-form` `useFieldArray` (NET-NEW use this phase — the event outcomes editor) | RHF (already a dep) |
| Icon | `lucide-react` — `Loader2` (spinners), `Plus`/`X`/`Trash2` (outcomes add/remove), `Search` (browse input) | `market-form.tsx` |
| Toast | `sonner` (admin success/failure) | `resolve-market-dialog.tsx` |
| Charts | Recharts (per-child price history, reused verbatim) | `price-history-chart.tsx` |
| Styling | Tailwind v4 (`@import "tailwindcss"` + `@theme inline`) | `globals.css` |
| Framework | Next 16 App Router, React 19; Server-Component pages → `"use client"` islands; SSR reads `cache:"no-store"` | repo-wide |
| Brand | runtime `--brand-*` CSS-variable cascade injected once in `app/layout.tsx <head>`; utilities `bg-/text-/border-/ring-brand-primary` | `globals.css`, `layout.tsx` |

**No registry install this phase.** All primitives are vendored. No `npx shadcn add`, no third-party registry — see §Registry Safety.

---

## THE PER-OUTCOME FRAMING LOCK (the heart of this phase — EVT-02)

> This is the single non-negotiable rule. Get this wrong and the product visibly lies about probability.

1. **Each outcome of a multi-outcome event is an INDEPENDENT binary market.** On the event detail page, every outcome renders as its **own row** with its **own YES probability** (0–100%), shown on its **own bar** (the reused `OddsDisplay` rendering that outcome's YES vs its OWN NO complement — a truthful per-binary split). 
2. **NEVER a single distribution bar summing to 100% across outcomes.** No stacked bar, no normalized share-of-event, no "pie". Live Polymarket data sums to <1 across many outcomes (≈0.45 across 60) — a 100%-stacked bar would visibly lie. This is an explicit **anti-feature** (REQUIREMENTS §Out of Scope).
3. **Display-only; no cross-outcome normalization.** The YES price shown per row is the child market's `yes_price` verbatim (rounded to a whole percent for display only). The rows do not sum to anything and must never be made to.
4. **The event card** (catalog grid, EVT-04) shows the **top 2–4 outcomes** each with its own independent YES %, plus "+N more" — again, never a single 100% bar.
5. Color is never the sole signal: every probability carries its numeric label.

Any planner/executor/reviewer output that introduces a summed/stacked/normalized outcome bar is a **BLOCK**, not a flag.

---

## Component Inventory (clone map — the executor's spine)

Each new component clones a NAMED existing file; copy the structure/tokens/states/a11y verbatim and swap the data source.

| New file | Clone source | What changes | Req |
|----------|--------------|--------------|-----|
| `lib/catalog.ts` | `lib/api.ts` (whole module: `apiBase()` + `cache:"no-store"` + typed `MarketNotFound` throw + format helpers) | `fetchCatalog({q,category,status,sort})` → `CatalogItem[]`; `fetchEvent(slug)` → `EventDetail` (throws `EventNotFound` on 404); `fetchCategories()` → `string[]`; + pure adapter `catalogMarketToMarketItem(item)` so the binary `MarketCard` renders a `type:"market"` catalog item | BRW-01..05 |
| `lib/admin-events-types.ts` | `lib/admin-markets-types.ts` | the event request/response types (`CreateEventRequest`, `UpdateEventRequest`, `EventChildRead`, `EventCreatedResponse`/`EventDetailResponse`, `ResolveEventRequest`, `VoidEventRequest`, `ReverseEventRequest`, `EventActionResponse`, `OutcomeInput`, `EVENT_LOCKED`) | EVA-01..05 |
| `lib/admin-events-api.ts` | `lib/admin-markets-api.ts` (`"use server"` Bearer-forward `bearerHeader()`/`adminApiFetch<T>`) | `createEvent` / `updateEvent` (surfaces 423) at **bare** `/admin/events`; `resolveEvent`/`voidEvent`/`reverseEvent` carry the `confirm` flag (preview vs execute). NO `/api/v1` prefix (bare, mirrors settlement) — encode per-call, URL-tested | EVA-01..05 |
| `components/catalog/event-card.tsx` | NET-NEW, built from `Card`/`CardHeader`/`CardContent`/`CardFooter` + a per-outcome row using `OddsDisplay`-style YES% (see §Event card) | the distinct multi-outcome card | EVT-04 |
| `components/catalog/catalog-controls.tsx` | NET-NEW client island using shadcn `Input`/`Select` + `useRouter`/`useSearchParams`/`usePathname` | debounced search → URL; category chip row; status + sort `Select`s → URL | BRW-01..04 |
| `app/page.tsx` (EDIT) | existing homepage Server Component | swap `MarketList`(→`/markets`) for the catalog browse: read `searchParams`, `fetchCatalog`+`fetchCategories`, render `<CatalogControls>` + a `MarketGrid` of (`EventCard` \| adapter→`MarketCard`) + explicit empty state | BRW-01..06, EVT-04 |
| `app/events/[slug]/page.tsx` | clone `app/markets/[slug]/page.tsx` (SSR `Promise.allSettled`, `cookies()→xpredict_session`, `grid grid-cols-1 lg:grid-cols-3 gap-8`, sticky right rail, header H1 `text-3xl font-semibold tracking-tight` + `SourceBadge` + status badge) | fetch `fetchEvent(slug)` (404→not-found state); SSR-fetch the DEFAULT child's `fetchMarket(child_slug)`+`fetchPriceHistory`; render `<EventDetailView>` | EVT-02,03,05 |
| `app/events/[slug]/error.tsx` | clone `app/markets/[slug]/error.tsx` | event error boundary copy | — |
| `components/event/event-detail-view.tsx` | NET-NEW client island | left = independent `OutcomeRow`s; right (sticky) = selected child's `MarketDetailLiveOdds` + `OrderEntryForm` + `PriceHistorySection`; on select → client `fetchMarket(child_slug)`+`fetchPriceHistory`; **WS cap = one socket (selected only)** | EVT-02,03,05 |
| `components/event/outcome-row.tsx` | NET-NEW, uses `OddsDisplay` (reused) | one outcome: label + own YES% + own bar + status chip + selected highlight (brand ring) + `onSelect` (button, keyboard-accessible) | EVT-02 |
| `components/admin/event-form.tsx` | clone `components/admin/market-form.tsx` (RHF+zod+`Form*`+`Loader2`+sonner+422→`setError`) | add a `useFieldArray` **outcomes** editor (min 2 `{label, initial_odds∈(0,1)}`, add/remove); title/category/deadline/resolution_criteria; create→`createEvent`, edit→`updateEvent`; on **423** disable the outcomes editor + locked helper | EVA-01,02 |
| `components/admin/event-detail-admin-actions.tsx` | clone `components/admin/market-detail-actions.tsx` | status-gated (derived: `open`/`partially_resolved`→Resolve+Void; `resolved`/`partially_resolved`→Reverse); hosts `EventForm` edit + the 3 dialogs; `router.refresh()` after mutation | EVA-02..05 |
| `components/admin/resolve-event-dialog.tsx` | clone `components/admin/resolve-market-dialog.tsx` | outcome `Select` (label → `yes_outcome_id`) + justification; **server two-step**: open→`confirm:false` preview (winners/losers/projected_status) → operator confirm→`confirm:true` execute | EVA-03 |
| `components/admin/void-event-dialog.tsx` | clone `resolve-market-dialog.tsx` (drop the Select) | justification + server two-step preview (winners:0/losers:all) → execute | EVA-04 |
| `components/admin/reverse-event-dialog.tsx` | clone `reverse-settlement-dialog.tsx` | justification + server two-step preview (`settled_children_to_reverse`) → execute; reverse-copy-guard body | EVA-05 |
| `app/admin/events/page.tsx` | clone `app/admin/markets/page.tsx` shell | list HOUSE events from the PUBLIC catalog filtered `type:"event" && source:"HOUSE"`; rows link to `/admin/events/{slug}`; "Create event" → `/admin/events/new` | EVA-* |
| `app/admin/events/new/page.tsx` | clone `app/admin/markets/new/page.tsx` | renders `<EventForm mode="create"/>` | EVA-01 |
| `app/admin/events/[slug]/page.tsx` | clone `app/admin/markets/[id]/page.tsx` | `fetchEvent(slug)` → `EventDetail`; header + `<EventDetailAdminActions event={...}/>` | EVA-02..05 |
| `components/admin/admin-nav.tsx` (EDIT) | existing | add `{ href:"/admin/events", label:"Events" }` to the `LINKS` array | EVA nav |

**Reused as-is (do NOT re-specify):** `OrderEntryForm` + `BetConfirmDialog` + `placeBetAction`, `PriceHistorySection` + `PriceHistoryChart`, `useMarketSocket` + `MarketDetailLiveOdds`, `OddsDisplay`, `SourceBadge`, `LiveIndicator`, `MarketCard`, `MarketGrid`, `MarketStatusBadge`, all shadcn primitives, `settlement-dialog-utils.isSessionExpiredError`, `fetchMarket`/`fetchPriceHistory` (`lib/api.ts`).

### Endpoint contract (the prefix split — encode per call)

| Capability | Prefix | Full path |
|------------|--------|-----------|
| Catalog browse / event detail / categories | `/api/v1` | `GET /api/v1/catalog?q&category&status&sort`, `GET /api/v1/events/{slug}`, `GET /api/v1/categories` |
| Child market read / price-history (per outcome) | `/api/v1` | `GET /api/v1/markets/{child_slug}`, `/api/v1/markets/{child_slug}/price-history` |
| Admin event create / edit | **bare** | `POST /admin/events`, `PATCH /admin/events/{group_id}` |
| Admin event resolve / void / reverse | **bare** | `POST /admin/events/{group_id}/resolve\|void\|reverse` (body `{…, confirm}`) |

A URL-contract unit test (`lib/__tests__/admin-events-api.test.ts`, clone of `admin-markets-api.test.ts`) locks the bare `/admin/events` prefix + the `confirm` flag passthrough.

---

## Surface Contracts

### Surface 1 — Catalog browse (`/`) — BRW-01..06, EVT-04

**Page (`app/page.tsx`, Server Component):** shell `w-full max-w-6xl mx-auto px-4 sm:px-6 py-12`; H1 **Markets** (`text-xl font-semibold mb-8`, unchanged). Reads `searchParams` (`q`, `category`, `status`, `sort`), `Promise.allSettled([fetchCatalog(params), fetchCategories()])` (degrade categories → `[]`, catalog error → error block). Renders `<CatalogControls categories status sort q />` then either a `<MarketGrid>` of cards or the empty state.

**Controls (`catalog-controls.tsx`, client):** a filter bar `flex flex-wrap items-end gap-4`:
- **Search** — `Input` with a `Search` icon, `placeholder="Search markets…"`, debounced ~300ms → `router.replace(pathname?q=…)`. Controlled off the URL `q`.
- **Category chips** — a horizontally scrollable row: an **"All"** chip + one chip per `categories` entry (the API returns only non-empty categories → CAT-06 honored automatically). Active chip = `bg-brand-primary text-brand-primary-foreground`; inactive = `bg-zinc-100 text-zinc-700 hover:bg-zinc-200`. Chip click → set/clear `?category`.
- **Status `Select`** — All / Open / Closing soon / Resolved → `?status=` (`open|closing_soon|resolved`; "All" clears).
- **Sort `Select`** — Volume / Closing soonest / Newest → `?sort=` (default `volume`).
- Changing any control resets nothing else (filters compose); search debounced, selects immediate.

**Grid:** reuse `MarketGrid` (`grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4`, framer stagger). For each item: `item.type === "event" ? <EventCard event={item}/> : <MarketCard market={catalogMarketToMarketItem(item)}/>`.

**Empty state (BRW-05):** when `items.length === 0`, a centered block (reuse the shipped copy): heading **No markets found**, body **No markets match your current filters. Try adjusting the search or filter criteria.** Never an error for a valid zero-result filter combination.

### Surface 2 — Event card (`event-card.tsx`) — EVT-04

A `Card` distinct from `MarketCard`:
- Header: event **title** (`text-base font-semibold leading-snug line-clamp-2`, stretched `Link` to `/events/{slug}`) + a small **"Event · {N} outcomes"** `Badge` (top-right, `relative z-10`).
- Content: the **top 2–4 outcomes** (sorted by YES desc) each as a compact row — `label` (truncate) + its own **YES %** (right, `tabular-nums`) + a thin own-bar (`OddsDisplay`-style YES fill). When `outcomes.length > 4`, a final muted **"+{N} more"** row. **Never a single 100% bar.**
- Footer: `Vol: {formatVolume}` + deadline + `SourceBadge`. Same hover/focus affordances as `MarketCard` (`hover:-translate-y-0.5 hover:shadow-md focus-within:ring-2 focus-within:ring-brand-primary`).

### Surface 3 — Event detail (`/events/[slug]`) — EVT-02, EVT-03, EVT-05 + WS cap

**Page (Server):** `fetchEvent(slug)`; on `EventNotFound` → the "Event not found" state (clone the market 404 state, "Back to markets" → `/`). Header: H1 `text-3xl font-semibold tracking-tight` (event title) + `SourceBadge` + a derived-status badge (`open`/`partially_resolved`/`resolved`/`void`). Compute the DEFAULT outcome (first OPEN, highest YES; else first); SSR `Promise.allSettled([fetchMarket(default.child_slug), fetchPriceHistory(default.child_slug,"7d")])`. `cookies()→isAuthenticated`. Render `<EventDetailView event default-child default-history isAuthenticated/>`.

**`EventDetailView` (client):** `grid grid-cols-1 gap-8 lg:grid-cols-3`.
- **LEFT (`lg:col-span-2`, `min-w-0`):** the **outcome list** — every outcome as an independent `OutcomeRow` (`label` + own YES% + own bar + `child_status` chip). The selected row carries a brand ring. **This is the per-outcome framing lock made visual.**
- **RIGHT (`lg:col-span-1 lg:sticky lg:top-8`):** the **selected-outcome panel** — a `Card` titled with the selected outcome label, containing `MarketDetailLiveOdds` (the **single** live socket — `marketId` = selected child) + the reused `OrderEntryForm` (selected child's full YES+NO outcomes, `min/max stake`, status) + `PriceHistorySection` (keyed `child_slug`). 
- **Selection:** clicking an `OutcomeRow` selects it → client `fetchMarket(child_slug)` (+ `fetchPriceHistory`) → re-render the panel; a brief loading state on the panel while fetching. Default selection is SSR-ready (no flash). **At most one child socket is ever open** (the selected one) — criterion 3's storm-proof cap, regardless of outcome count.
- Closed/resolved children: `OrderEntryForm` already disables on non-OPEN status; the row shows the status chip.

### Surface 4 — Admin event ops (`/admin/events*`) — EVA-01..05

- **List (`/admin/events`):** Server Component; `fetchCatalog()` filtered `type:"event" && source:"HOUSE"` → a simple table/list (title, category, derived status, outcome count, "Manage"). Top-right **Create event** → `/admin/events/new`. Empty → "No house events yet." Rows link to `/admin/events/{slug}`.
- **Create (`/admin/events/new`):** `<EventForm mode="create"/>`.
- **Manage (`/admin/events/[slug]`):** `fetchEvent(slug)` → `EventDetail` (its `id` = `group_id`). Header (title + status badge) + `<EventDetailAdminActions event/>` hosting the **edit form** (`EventForm mode="edit"`, prefilled outcomes from `event.outcomes`) + status-gated **Resolve / Void / Reverse** buttons + their dialogs.
- **`EventForm` outcomes editor:** `useFieldArray` (min 2). Each row: a `label` `Input` + an `initial_odds` `Input` (`inputMode="decimal"`, helper "0–1, e.g. 0.5") + a remove `X` button (disabled when only 2 remain). An **"Add outcome"** `Button` (`Plus`). On edit, `outcomes` is a whole-list replace. On **423 `{code:"EVENT_LOCKED"}`**, disable the entire outcomes editor + show **"Outcomes lock once the event has a bet."** (mirrors the criteria-lock helper).
- **Dialogs (server two-step):** Resolve = outcome `Select` (each `event.outcomes[i].label` → value `yes_outcome_id`) + justification → call `resolveEvent(groupId,{winning_outcome_id, justification, confirm:false})` on open → render the preview (`{winners} win, {losers} lose → {projected_status}`) → **Confirm resolve** (destructive) calls `confirm:true`. Void/Reverse the same, justification-only. All justifications mandatory (`trim().length>=1`).

---

## Copywriting Contract (reuse Phase-12 conventions)

| Element | Copy |
|---------|------|
| Browse empty | **No markets found** / **No markets match your current filters. Try adjusting the search or filter criteria.** |
| Event 404 | **Event not found** / "This event doesn't exist or is no longer available." + "Back to markets" → `/` |
| Event load error (`error.tsx`) | **Unable to load this event** / "Something went wrong. Try refreshing the page." |
| Event card badge | **Event · {N} outcomes** ; overflow row **+{N} more** |
| Admin events empty | **No house events yet.** |
| Outcomes lock helper (423) | **Outcomes lock once the event has a bet.** |
| Justification required | **A justification is required.** |
| Resolve/Void/Reverse preview | resolve **"{winners} winning, {losers} losing positions → resolved"** · void **"All {losers} positions settle NO → void"** · reverse **"{n} settled outcomes will be reversed → open"** |
| Create event CTA / toast | **Create event** / **Event created.** / **Couldn't create the event. Please try again.** |
| Edit event toast | **Event updated.** / **Couldn't save changes. Please try again.** (locked → **Outcomes are locked once the event has a bet.**) |
| Resolve toast | **Event resolved.** / **Couldn't resolve the event. Please try again.** |
| Void toast | **Event voided.** / **Couldn't void the event. Please try again.** |
| Reverse toast | **Event settlement reversed.** / **Couldn't reverse the event. Please try again.** |
| Session expired (401/403) | **Your session expired. Please sign in again.** |

All copy English; play-money framing (no deposit/cash/casino). Money via the string `formatVolume`/`formatMoney` helpers.

---

## Color / Brand (BRW-06)

Inherit the neutral-zinc + single `--brand-*` accent system. **Every new surface uses the brand utilities** (`bg-/text-/border-/ring-brand-primary`) or `var(--brand-primary,…)` for SVG/inline bars — never a hardcoded hue:
- Active category chip → `bg-brand-primary text-brand-primary-foreground`.
- Selected `OutcomeRow` highlight → `ring-2 ring-brand-primary` (matches `MarketCard` focus).
- Per-outcome YES bars reuse `OddsDisplay` (YES segment is already `bg-brand-primary`).
- The reused price chart already strokes `var(--brand-primary,…)`.
- Primary CTAs (`Create event`, `Save changes`) use the `default` (zinc-900) Button; destructive confirms (`Confirm resolve/void/reverse`) use `destructive` (red-500) — same as Phase 12 (do NOT introduce brand-colored buttons).

No per-page provider — surfaces inherit theming from the root-layout cascade. A `/admin/branding` palette change re-skins every new surface on next navigation (verify in §UI-review).

---

## Responsive + Accessibility (inherit — do not regress)

- Page gutter `px-4 sm:px-6`; widths `max-w-6xl mx-auto`; two-column detail `grid grid-cols-1 lg:grid-cols-3 gap-8` + right rail `lg:sticky lg:top-8` + LEFT `min-w-0`. Filter bar `flex flex-wrap items-end gap-4`. Category chip row scrolls (`overflow-x-auto`) on narrow. Baseline ≥360px.
- `OutcomeRow` is a real `<button>` (or `role="button"` + `tabIndex=0` + Enter/Space) with `aria-pressed`/`aria-current` for the selected state and an `aria-label` ("{label}, {pct}% YES"); color never the sole signal (numeric % + status text always present).
- Dialogs inherit `Dialog` focus-trap/ESC; mandatory justification uses `role="alert"` + `aria-invalid`; stay-open-during-submit; `Loader2` spinner.
- Event-card stretched-link pattern (title `Link after:absolute after:inset-0`, badge/source `relative z-10`) — no nested `<a>`.
- Search `Input` has an accessible label; category chips are `aria-pressed` toggles; selects use shadcn `Select` (labelled).

---

## Registry Safety

| Registry | Blocks used | Gate |
|----------|-------------|------|
| shadcn official (already vendored) | none added — all primitives (input, select, card, dialog, form, textarea, badge, button, label, separator, tabs, skeleton) already present | not required (no install) |
| third-party | **none** | N/A |

No `npx shadcn add`, no third-party registry. Zero new dependencies (RHF `useFieldArray` + the listed `lucide-react` icons already ship with their packages).

---

## Open Questions (recommended default given — non-blocking)

1. **Selected-outcome panel: sticky right rail vs inline expansion?** → **Right rail** (`lg:sticky lg:top-8`), mirroring `markets/[slug]`. Zero new layout primitives; "the place where you'd bet" maps cleanly. Inline expansion would need new accordion layout — avoid.
2. **Retire `MarketList` (only used by `/`)?** → **Retire it + its test**, replace with the catalog browse, reusing `MarketCard` for `type:"market"` items via the adapter. Avoids dead code. (Verify no other import first.)
3. **Default-selected outcome when all children are closed/resolved?** → first by YES desc (still selectable; the order form self-disables on non-OPEN). The page stays coherent for a fully-resolved event.

---

## Checker Sign-Off
- [ ] Dim 1 Copywriting: PASS
- [ ] Dim 2 Visuals (incl. the per-outcome framing LOCK): PASS
- [ ] Dim 3 Color / Brand (BRW-06): PASS
- [ ] Dim 4 Typography (0 net-new): PASS
- [ ] Dim 5 Spacing (0 net-new): PASS
- [ ] Dim 6 Registry Safety: PASS

**Approval:** auto-approved (autonomous mode); the per-outcome framing LOCK is the gating visual invariant.
</content>
