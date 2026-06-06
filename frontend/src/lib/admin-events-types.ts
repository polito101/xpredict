/**
 * Shared TypeScript types for the admin event Server Actions (Phase 17).
 *
 * `lib/admin-events-api.ts` is a `"use server"` module, which may export ONLY
 * async functions — so every shared type lives here (mirrors the
 * `admin-markets-api.ts` / `admin-markets-types.ts` split).
 *
 * Types transcribe the merged Phase-16 admin event contract
 * (`backend/app/settlement/event_schemas.py`). Money/odds are STRINGS on the
 * wire (never floats).
 */

/** One outcome when creating/editing an event (initial_odds in (0,1)). */
export interface OutcomeInput {
  label: string;
  initial_odds: string;
}

/** `POST /admin/events` body. `outcomes` must have ≥2 entries. */
export interface CreateEventRequest {
  title: string;
  category?: string | null;
  deadline: string; // ISO; backend requires a future datetime
  resolution_criteria?: string | null;
  slug?: string | null;
  outcomes: OutcomeInput[];
}

/** `PATCH /admin/events/{group_id}` body — all optional; outcomes = whole-list replace (≥2). */
export interface UpdateEventRequest {
  title?: string;
  category?: string | null;
  deadline?: string;
  outcomes?: OutcomeInput[];
}

/** One child market on an event create/edit response. */
export interface EventChildRead {
  market_id: string;
  label: string;
  slug: string;
  status: string;
  yes_outcome_id: string | null;
  yes_price: string;
}

/** `POST /admin/events` (201) / `PATCH …` response. */
export interface EventCreatedResponse {
  id: string;
  title: string;
  slug: string;
  category: string | null;
  source: string;
  deadline: string | null;
  outcomes: EventChildRead[];
}

/** Same shape as the create response (the PATCH return). */
export type EventDetailResponse = EventCreatedResponse;

/** `POST /admin/events/{group_id}/resolve` body. */
export interface ResolveEventRequest {
  winning_outcome_id: string;
  justification: string;
  confirm?: boolean;
}

/** `POST /admin/events/{group_id}/void` body. */
export interface VoidEventRequest {
  justification: string;
  confirm?: boolean;
}

/** `POST /admin/events/{group_id}/reverse` body. */
export interface ReverseEventRequest {
  justification: string;
  confirm?: boolean;
}

/**
 * Shared response for resolve/void/reverse — covers BOTH the `confirm:false`
 * preview (winners/losers/settled_children_to_reverse) and the `confirm:true`
 * execute (children_settled/children_failed).
 */
export interface EventActionResponse {
  preview: boolean;
  group_id: string;
  child_count: number;
  winners?: number | null;
  losers?: number | null;
  settled_children_to_reverse?: number | null;
  children_settled?: number | null;
  children_failed?: string[] | null;
  projected_status: string;
}

/** The backend error code returned (HTTP 423) once an event has a bet. */
export const EVENT_LOCKED = "EVENT_LOCKED";

/**
 * True when a thrown admin-events error is the 423 edit-lock. The `"use server"`
 * layer throws `Error("API error: 423")`; a richer payload may carry the
 * `EVENT_LOCKED` code — match either so the form can render the lock state
 * instead of a generic failure toast.
 */
export function isEventLockedError(err: unknown): boolean {
  const message = err instanceof Error ? err.message : String(err ?? "");
  return /\b423\b/.test(message) || message.includes(EVENT_LOCKED);
}
