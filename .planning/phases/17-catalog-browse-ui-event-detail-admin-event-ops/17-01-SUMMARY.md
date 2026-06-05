# Plan 17-01 Summary — Data Layer

**Status:** ✅ Complete
**Completed:** 2026-06-06

## What shipped
- `lib/catalog.ts` — public catalog client mirroring `lib/api.ts`: types (`CatalogItem`, `CatalogOutcome`, `EventDetail`, `EventOutcomeRead`, `PublicCatalogStatus`, `CatalogSort`, `EventDerivedStatus`), `fetchCatalog`/`fetchEvent`/`fetchCategories`, `EventNotFound`, and the `catalogMarketToMarketItem` adapter (deadline-null guard).
- `lib/admin-events-types.ts` — admin event request/response types + `EVENT_LOCKED` + `isEventLockedError`.
- `lib/admin-events-api.ts` — `"use server"` Bearer-forward actions (`createEvent`/`updateEvent`/`resolveEvent`/`voidEvent`/`reverseEvent`) at the BARE `/admin/events` prefix; resolve/void/reverse carry the `confirm` flag.
- `lib/__tests__/catalog.test.ts` (6) + `lib/__tests__/admin-events-api.test.ts` (9).

## Verification
- `tsc --noEmit` clean (whole project).
- `vitest run` (both files) — 15/15 green.
- `eslint` clean for all 5 files.
- URL-contract: bare `/admin/events` prefix (no `/api/v1`) + `confirm` flag passthrough + 423→`isEventLockedError` all asserted.

## Notes
- Installed `node_modules` via `corepack pnpm@9.15.0 install --frozen-lockfile` (non-destructive; lockfile unchanged).
- The adapter omits a synthetic NO outcome by design (MarketCard derives NO as the YES complement; the catalog card never offers a bet path).
</content>
