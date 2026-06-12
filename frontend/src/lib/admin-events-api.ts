/**
 * Plan 17-01 — Admin event-operations API helper (Server Actions).
 *
 * Clone of `lib/admin-markets-api.ts`: `"use server"`, so the `admin_jwt`
 * HttpOnly cookie is read SERVER-SIDE via `next/headers > cookies()` and
 * forwarded as `Authorization: Bearer <token>`; the token never reaches client
 * JS. Client components call these exported async functions directly.
 *
 * PREFIX: the admin event surface is mounted at the BARE `/admin/events…`
 * prefix (NO `/api/v1`), mirroring the settlement router — distinct from the
 * `/api/v1/admin/markets` CRUD prefix. Each wrapper encodes the full bare path;
 * `admin-events-api.test.ts` is the URL-contract guard.
 *
 * TWO-STEP CONFIRM: resolve/void/reverse carry a `confirm` flag — `false`/absent
 * returns a non-mutating preview, `true` executes (same `EventActionResponse`).
 *
 * EDIT-LOCK: a `PATCH` after the first bet returns HTTP 423; `adminApiFetch`
 * throws `Error("API error: 423")`, which `isEventLockedError` (in
 * `admin-events-types.ts`) decodes so the form renders the lock.
 *
 * A `"use server"` file may export only async functions, so all shared types
 * live in `./admin-events-types`.
 */
"use server";

import { cookies } from "next/headers";

import type {
  CreateEventRequest,
  UpdateEventRequest,
  EventCreatedResponse,
  EventDetailResponse,
  ResolveEventRequest,
  VoidEventRequest,
  ReverseEventRequest,
  EventActionResponse,
} from "./admin-events-types";

import { getBackendUrl } from "./config";

// Bare prefix — NO `/api/v1` (mirrors the settlement router).
const EVENTS_PREFIX = "/admin/events";

/** Serializable subset of RequestInit safe across the action boundary. */
type AdminFetchInit = {
  method?: string;
  body?: string;
  headers?: Record<string, string>;
};

async function bearerHeader(): Promise<Record<string, string>> {
  const store = await cookies();
  const token = store.get("admin_jwt")?.value;
  if (!token) {
    throw new Error("Not authenticated");
  }
  return { Authorization: `Bearer ${token}` };
}

/**
 * Core admin fetch — reads admin_jwt, forwards as Bearer, parses JSON. Throws
 * `Error("API error: <status>")` on a non-2xx (the status is preserved in the
 * message so callers branch on, e.g., 423 lock / 409 mirrored / 422 bad input).
 */
async function adminApiFetch<T = unknown>(
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

const JSON_HEADERS = { "Content-Type": "application/json" };

/** Create a house multi-outcome event (EVA-01). `POST /admin/events`. */
export async function createEvent(
  body: CreateEventRequest,
): Promise<EventCreatedResponse> {
  return adminApiFetch<EventCreatedResponse>(EVENTS_PREFIX, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

/**
 * Edit a house event (EVA-02). `PATCH /admin/events/{group_id}`.
 * After the first child bet the backend returns 423 → `isEventLockedError`.
 */
export async function updateEvent(
  groupId: string,
  body: UpdateEventRequest,
): Promise<EventDetailResponse> {
  return adminApiFetch<EventDetailResponse>(`${EVENTS_PREFIX}/${groupId}`, {
    method: "PATCH",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

/**
 * Resolve a house event (EVA-03). `POST /admin/events/{group_id}/resolve`.
 * `confirm:false` → non-mutating preview; `confirm:true` → execute.
 */
export async function resolveEvent(
  groupId: string,
  body: ResolveEventRequest,
): Promise<EventActionResponse> {
  return adminApiFetch<EventActionResponse>(
    `${EVENTS_PREFIX}/${groupId}/resolve`,
    { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body) },
  );
}

/**
 * Void a house event (EVA-04). `POST /admin/events/{group_id}/void`.
 * Every child settles NO (explicitly NOT a stake refund). Two-step `confirm`.
 */
export async function voidEvent(
  groupId: string,
  body: VoidEventRequest,
): Promise<EventActionResponse> {
  return adminApiFetch<EventActionResponse>(`${EVENTS_PREFIX}/${groupId}/void`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

/**
 * Reverse an event resolution (EVA-05). `POST /admin/events/{group_id}/reverse`.
 * Compensating ledger entries restore the pre-settlement state. Two-step `confirm`.
 */
export async function reverseEvent(
  groupId: string,
  body: ReverseEventRequest,
): Promise<EventActionResponse> {
  return adminApiFetch<EventActionResponse>(
    `${EVENTS_PREFIX}/${groupId}/reverse`,
    { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body) },
  );
}
