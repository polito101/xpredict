# Plan 17-04 Summary — Admin Event Ops

**Status:** ✅ Complete
**Completed:** 2026-06-06

## What shipped
- `components/admin/event-form.tsx` — create/edit form (clone of `market-form.tsx`) with a dynamic `useFieldArray` outcomes editor (min 2, add/remove with a 2-floor, each `{label, initial_odds∈(0,1)}`). Create→`createEvent`; edit→`updateEvent` (outcomes whole-list replace). A **423** locks the whole form + shows the lock banner (EVA-01/02).
- `components/admin/{resolve,void,reverse}-event-dialog.tsx` — the **server-driven two-step**: "Preview impact" calls the action with `confirm:false` (non-mutating; renders projected winners/losers/settled-to-reverse + status), then the destructive confirm calls `confirm:true`. Mandatory justification; editing inputs clears the preview; 409 (mirrored)/session-expired handled (EVA-03/04/05). Reverse uses the copy-guard.
- `components/admin/event-detail-admin-actions.tsx` — status-gated action host (open/partially_resolved→Resolve+Void; resolved/partially_resolved→Reverse; mirrored→read-only) + the edit form + dialogs + `router.refresh()`.
- `app/admin/events/{page,new/page,[slug]/page}.tsx` — list (filtered public catalog: `type:event && source:HOUSE`), create, manage (loads via `fetchEvent(slug)`).
- `components/admin/admin-nav.tsx` — added the **Events** link.
- Tests: `event-form.test.tsx` (4), `void-event-dialog.test.tsx` (2, the full two-step), `resolve-event-dialog.test.tsx` (1, outcome-required).

## Verification
- `tsc --noEmit` clean; `eslint` exit 0; `vitest` 7/7 green.
- The 3 dialogs' reset-on-open `useEffect` produces the same `set-state-in-effect` **warning** as the merged Phase-12 dialogs (`resolve-market-dialog`/`reverse-settlement-dialog`) — a pre-existing, CI-accepted house pattern; left consistent.

## Decisions / limitations
- No admin event-list/get endpoint exists → the list uses the public catalog (house events only); the manage page loads via the public `/events/{slug}` (its `id` = group_id). A dedicated admin event-list endpoint (drafts, bet counts) is deferred to a future backend phase.
- Edit-lock is reactive (no `bet_count` on the event read): discovered on submit via the 423 → whole-form lock (the backend blocks the entire PATCH once any child has a bet).
- The resolve dialog's full two-step (with the Radix outcome `Select`) is covered functionally by the void dialog test (identical flow, no portal); the resolve test covers the outcome-required gate.
</content>
