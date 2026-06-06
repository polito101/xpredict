# Plan 17-02 Summary — Catalog Browse UI

**Status:** ✅ Complete
**Completed:** 2026-06-06

## What shipped
- `components/catalog/event-card.tsx` — the distinct multi-outcome `EventCard` (EVT-04): "Event · N outcomes" badge + top ≤4 outcomes each with its OWN independent YES % + own bar + "+N more", links `/events/{slug}`. **No summed/stacked bar** (framing LOCK).
- `components/catalog/catalog-controls.tsx` — `"use client"` browse controls: debounced (~300ms) search → URL, category chip row (only provided categories + "All"), status + sort `Select`s → URL. Active chip uses `bg-brand-primary` (BRW-06). Input/URL sync via the render-time state-adjustment pattern (no effect).
- `app/page.tsx` — rewritten as the curated catalog browse: Server Component reads `searchParams`, `Promise.allSettled([fetchCategories, fetchCatalog])`, renders controls + a `MarketGrid` of `EventCard | adapter→MarketCard` + explicit empty/error states (BRW-05).
- `app/loading.tsx` — route loading skeleton (reuses `MarketListSkeleton`, formerly the homepage Suspense fallback).
- Removed the orphaned `components/market-list.tsx` (only the old homepage imported it; no test existed).
- Tests: `event-card.test.tsx` (5), `catalog-controls.test.tsx` (5).

## Verification
- `tsc --noEmit` clean; `eslint` clean (the input-sync `set-state-in-effect` warning fixed via render-time adjustment); `vitest run src/components/catalog` 10/10 green.
- The "+N more" / top-4 / independent-percent (50%+45%+40%=135%) assertions prove the framing LOCK; the controls assert empty-categories-never-render + debounced `?q` + `?category` URL drive.

## Decisions
- The "Markets" player-nav link already points to `/`, so upgrading `/` keeps nav coherent (no nav change).
- `MarketListSkeleton` repurposed into `app/loading.tsx` rather than deleted (preserves loading UX, no orphan).
- Radix `Select` dropdown interaction not unit-tested (jsdom/portal flakiness); the URL-driving paths (chips + debounced search) are covered.
</content>
