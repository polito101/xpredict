---
phase: 17
status: pass
type: advisory
audited: 2026-06-06
method: retroactive 6-pillar code audit vs 17-UI-SPEC.md
score: 6/6 PASS
---

# Phase 17 — UI Review (6-pillar, advisory)

Retroactive code audit of the new frontend surfaces (catalog browse, event card, event detail, admin event ops) against `17-UI-SPEC.md`. Advisory/non-blocking. Runtime confirmation (palette swap, visual distinctness, truthful rendering on real data) is recommended at demo time but the structure is verified here.

## Pillar 1 — Copywriting: **PASS**
- Empty/error/toast/justification copy matches the contract: "No markets found / No markets match your current filters…", "Event not found / This event doesn't exist…", "Unable to load this event", toasts (Event created/updated/resolved/voided/reversed + failure variants), "A justification is required.", session-expired toast.
- **Intentional deviation:** the edit-lock banner reads "This event has bets and can no longer be edited." (not the UI-SPEC's "Outcomes lock once the event has a bet.") because the backend 423 blocks the *entire* PATCH, not just outcomes — the new copy is more accurate. PASS.
- All copy English; play-money framing; money via the string `formatVolume`/`formatDeadline` helpers.

## Pillar 2 — Visuals: **PASS (incl. the gating framing LOCK)**
- **Framing LOCK holds** — each outcome (card + detail rows) renders its own independent YES% bar; no stacked/normalized/sum-to-100 bar anywhere (confirmed by 2 reviewers + tests asserting >100% sums).
- Event card is distinct from the binary card (multi-row outcomes + "Event · N outcomes" badge + "+N more"); selected `OutcomeRow` uses the brand ring; explicit empty/error/loading states (`app/loading.tsx`, `CatalogEmpty`, `EventNotFoundState`, route `error.tsx`).

## Pillar 3 — Color / Brand (BRW-06): **PASS**
- Brand accents via `bg-/text-/border-/ring-brand-primary` (active chip, selected-row ring, YES bars); no hardcoded brand hue (audit clean).
- Semantic palette matches Phase-12: emerald=open/active, amber=partially_resolved/lock, zinc=neutral/resolved, red/rose=error/destructive. Destructive confirms use the `destructive` button (not a brand-colored button).

## Pillar 4 — Typography: **PASS (0 net-new)**
- Inherited roles only: `text-3xl` page H1 (event/market detail), `text-xl` admin list H1, `text-lg` section/card titles, `text-base` card titles, `text-sm` body, `text-xs` chips/labels; `tabular-nums` on every percentage. No new sizes/weights.

## Pillar 5 — Spacing: **PASS (0 net-new)**
- Inherited 4px scale: page shells `max-w-6xl mx-auto px-4 sm:px-6 py-12` (player) / `px-6 py-12` (admin); grid `gap-4` (cards) / `gap-8` (detail columns); filter bar `flex flex-wrap items-end gap-4`; chip row `gap-2 overflow-x-auto`; sticky right rail `lg:sticky lg:top-8`; `min-w-0` on the detail left column. No off-grid values introduced.

## Pillar 6 — Registry Safety: **PASS**
- Zero new dependencies; all shadcn primitives (input, select, card, dialog, form, textarea, badge, button, label) already vendored; `react-hook-form` `useFieldArray` + the `lucide-react` icons (Search/Plus/X/Loader2/ArrowLeft) ship with installed packages. No `npx shadcn add`, no third-party registry.

## Responsive / Accessibility (cross-cutting): **PASS**
- Baseline ≥360px; filter bar + chip row wrap/scroll; two-column detail collapses to one on mobile. `OutcomeRow` is a labelled `<button>` (`aria-pressed`/`aria-label`); category chips `aria-pressed` in a labelled `role="group"`; dialogs Radix-focus-trapped with `role="alert"` mandatory errors + `aria-invalid`; color never the sole signal.

**Overall: 6/6 PASS (advisory).** No blocking visual issues. One intentional, more-accurate copy deviation noted.
</content>
