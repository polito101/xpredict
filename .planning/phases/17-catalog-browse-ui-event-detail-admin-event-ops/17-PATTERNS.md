# Phase 17 — Patterns (new file → closest analog)

Every new file maps to a named existing analog. The executor clones the analog's structure, tokens, states, and a11y, swapping only the data source. Paths relative to repo root.

## Data layer

| New file | Closest analog | Pattern carried over |
|----------|----------------|----------------------|
| `frontend/src/lib/catalog.ts` | `frontend/src/lib/api.ts` | `apiBase()` server/browser split; `cache:"no-store"`; typed `EventNotFound` (cf. `MarketNotFound`); reuse `formatVolume`/`formatDeadline`; pure adapter. |
| `frontend/src/lib/admin-events-types.ts` | `frontend/src/lib/admin-markets-types.ts` | shared TS types extracted from the `"use server"` module (which may export only async fns). |
| `frontend/src/lib/admin-events-api.ts` | `frontend/src/lib/admin-markets-api.ts` | `"use server"`; `bearerHeader()` (`admin_jwt`→Bearer); `adminApiFetch<T>` throw-on-non-2xx; per-call full path (prefix split). |
| `frontend/src/lib/__tests__/catalog.test.ts` | `frontend/src/lib/__tests__/auth.test.ts` (fetch-mock style) | `vi.spyOn(globalThis,"fetch")`; assert URL + params; 404→throw. |
| `frontend/src/lib/__tests__/admin-events-api.test.ts` | `frontend/src/lib/__tests__/admin-markets-api.test.ts` | `vi.hoisted` cookie store; `vi.mock("next/headers")`; assert bare `/admin/events` URL + Bearer + `confirm` body. |

## Player surfaces

| New file | Closest analog | Pattern carried over |
|----------|----------------|----------------------|
| `frontend/src/app/page.tsx` (EDIT) | itself + `app/markets/[slug]/page.tsx` | Server Component reads `searchParams`; `Promise.allSettled`; degrade-to-empty; compose island + grid. |
| `frontend/src/components/catalog/catalog-controls.tsx` | `components/admin/markets-data-table.tsx` filter bar + `order-entry-form.tsx` Select usage | `flex flex-wrap items-end gap-4`; shadcn `Select`/`Input`; URL via `useRouter`/`useSearchParams`. |
| `frontend/src/components/catalog/event-card.tsx` | `components/market-card.tsx` | `Card` + stretched-link + `OddsDisplay` per outcome + footer; distinct multi-row layout + badge. |
| `frontend/src/components/catalog/event-card.test.tsx` | `components/__tests__/market-card.test.tsx` | `render`/`screen`; `vi.mock("next/link")`; assert top outcomes + "+N more" + `/events/{slug}` href. |
| `frontend/src/app/events/[slug]/page.tsx` | `app/markets/[slug]/page.tsx` | SSR parallel fetch; 404 state; `cookies()→isAuthenticated`; `grid lg:grid-cols-3`; sticky rail. |
| `frontend/src/app/events/[slug]/error.tsx` | `app/markets/[slug]/error.tsx` | client error boundary copy. |
| `frontend/src/components/event/event-detail-view.tsx` | `app/markets/[slug]/page.tsx` body + `price-history-section.tsx` (client state+refetch) | left list / right sticky panel; client `fetchMarket(child_slug)` on select; single socket. |
| `frontend/src/components/event/outcome-row.tsx` | `components/odds-display.tsx` consumer + `market-card.tsx` row | `<button>`/`role` + `aria-pressed`; own YES% + own bar + status chip; brand ring when selected. |
| `frontend/src/components/event/event-detail-view.test.tsx` | `components/order-entry-form.test.tsx` | mock `fetchMarket`/server action; assert independent rows (no single 100% bar), default selection, select→panel. |

## Admin surfaces

| New file | Closest analog | Pattern carried over |
|----------|----------------|----------------------|
| `frontend/src/components/admin/event-form.tsx` | `components/admin/market-form.tsx` | RHF+zod+`Form*`+`Loader2`+sonner+422→`setError`; + `useFieldArray` outcomes (min 2); 423→lock outcomes. |
| `frontend/src/components/admin/event-detail-admin-actions.tsx` | `components/admin/market-detail-actions.tsx` | status-gated buttons + edit form host + dialogs + `router.refresh()`. |
| `frontend/src/components/admin/resolve-event-dialog.tsx` | `components/admin/resolve-market-dialog.tsx` | outcome `Select` + justification + two-step; adapt to server preview/execute (`confirm`). |
| `frontend/src/components/admin/void-event-dialog.tsx` | `resolve-market-dialog.tsx` (no Select) | justification + server two-step. |
| `frontend/src/components/admin/reverse-event-dialog.tsx` | `components/admin/reverse-settlement-dialog.tsx` | justification + server two-step + reverse-copy-guard. |
| `frontend/src/app/admin/events/page.tsx` | `app/admin/markets/page.tsx` | Server Component shell; list from filtered catalog; "Create" CTA. |
| `frontend/src/app/admin/events/new/page.tsx` | `app/admin/markets/new/page.tsx` | renders the create form. |
| `frontend/src/app/admin/events/[slug]/page.tsx` | `app/admin/markets/[id]/page.tsx` | SSR fetch + header + actions island. |
| `frontend/src/components/admin/admin-nav.tsx` (EDIT) | itself | add a `LINKS` entry, keep active-highlight. |
| `frontend/src/components/admin/event-form.test.tsx` | `components/admin/__tests__/market-form.test.tsx` (or `branding-form.test.tsx`) | RHF render; add/remove outcome; submit body; 423 lock. |
| `frontend/src/components/admin/resolve-event-dialog.test.tsx` | `components/admin/__tests__/resolve-market-dialog.test.tsx` | mock the server action; preview→execute; justification required. |

## Cross-cutting conventions (apply to ALL new files)
- Money/odds = strings on the wire; round only for display.
- Brand accents via `bg-/text-/border-/ring-brand-primary` or `var(--brand-primary,…)` — never a hardcoded hue (BRW-06).
- Server Components for data + shells; `"use client"` islands for interactivity. Next 16 async `await params`/`searchParams`.
- Tests co-located or in `__tests__/`; mock `next/link`, server actions, `globalThis.fetch`/`next/headers`.
</content>
