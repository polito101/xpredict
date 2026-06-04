/**
 * Plan 12-02 — Admin market-operations API helper (Server Actions).
 *
 * Every admin market call from the frontend funnels through here. This module is
 * `"use server"`, so the `admin_jwt` HttpOnly cookie is read SERVER-SIDE via
 * `next/headers > cookies()` and forwarded as `Authorization: Bearer <token>`
 * to FastAPI. The token NEVER reaches client JS (threat T-12-05 — see
 * <threat_model> in 12-02-PLAN.md). Client components call these exported async
 * functions directly; they cannot read the HttpOnly cookie themselves.
 *
 * THE TWO-PREFIX LANDMINE (Pitfall 1 / threat T-12-06): market CRUD is mounted
 * at `/api/v1/admin/markets` (`markets/router.py:32-33`) but resolve / reverse /
 * force-settle live at the BARE `/admin/markets/{id}/...` prefix
 * (`settlement/router.py:46`, NO `/api/v1`). The SAME class of bug already
 * shipped + got caught for the recharge endpoint (`admin-api.ts` `rechargeWallet`).
 * Each wrapper below passes the FULL path per call so the split is explicit, and
 * `admin-markets-api.test.ts` is the URL-contract guard that locks it.
 *
 * Next constraint: a `"use server"` file may only export async functions, so
 * all shared types live in `./admin-markets-types`.
 *
 * BACKEND_URL is read from the server env (no `NEXT_PUBLIC_` prefix — it never
 * leaks into the client bundle), mirroring `lib/admin-api.ts`.
 */
"use server";

import { cookies } from "next/headers";

import type {
  PaginatedResponse,
  MarketListItem,
  MarketDetail,
  MarketCreateBody,
  MarketUpdateBody,
  ResolveMarketBody,
  ReverseBody,
  ForceSettleBody,
  MarketListParams,
} from "./admin-markets-types";
import { buildQuery } from "./admin-query";

function getBackendUrl(): string {
  return process.env.BACKEND_URL || "http://localhost:8000";
}

/** Serializable subset of RequestInit safe to pass across the action boundary. */
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
 * Core admin fetch — reads admin_jwt, forwards as Bearer, parses JSON.
 * Throws `Error("API error: <status>")` on a non-2xx response (the status
 * code is preserved in the message so callers can branch on, e.g., 422).
 */
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

// ---------------------------------------------------------------------------
// Market CRUD wrappers — KEEP the /api/v1 prefix (markets/router.py:32-33).
// ---------------------------------------------------------------------------

/** List markets. `GET /api/v1/admin/markets` → PaginatedResponse<MarketListItem>. */
export async function fetchMarkets(
  params: MarketListParams,
): Promise<PaginatedResponse<MarketListItem>> {
  const qs = buildQuery({
    source: params.source,
    status: params.status,
    category: params.category,
    page: params.page,
    page_size: params.page_size,
    sort_by: params.sort_by,
    sort_order: params.sort_order,
  });
  return adminApiFetch<PaginatedResponse<MarketListItem>>(
    `/api/v1/admin/markets${qs}`,
  );
}

/** Fetch one market (admin detail). `GET /api/v1/admin/markets/{id}`. */
export async function fetchMarketAdmin(id: string): Promise<MarketDetail> {
  return adminApiFetch<MarketDetail>(`/api/v1/admin/markets/${id}`);
}

/** Create a house market. `POST /api/v1/admin/markets` (body = MarketCreate). */
export async function createMarket(
  body: MarketCreateBody,
): Promise<MarketDetail> {
  return adminApiFetch<MarketDetail>(`/api/v1/admin/markets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** Edit a market. `PATCH /api/v1/admin/markets/{id}` (body = MarketUpdate). */
export async function updateMarket(
  id: string,
  body: MarketUpdateBody,
): Promise<MarketDetail> {
  return adminApiFetch<MarketDetail>(`/api/v1/admin/markets/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** Close a market early (ADM-04). `POST /api/v1/admin/markets/{id}/close` (no body). */
export async function closeMarket(id: string): Promise<MarketDetail> {
  return adminApiFetch<MarketDetail>(`/api/v1/admin/markets/${id}/close`, {
    method: "POST",
  });
}

// ---------------------------------------------------------------------------
// Settlement wrappers — BARE prefix, NO /api/v1 (settlement/router.py:46).
// This is the regression-guarded split; clone of the rechargeWallet pattern.
// ---------------------------------------------------------------------------

/** Resolve a house market (STL-02 / ADM-05). `POST /admin/markets/{id}/resolve`. */
export async function resolveMarket(
  id: string,
  body: ResolveMarketBody,
): Promise<unknown> {
  return adminApiFetch(`/admin/markets/${id}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** Reverse a settlement (STL-07). `POST /admin/markets/{id}/reverse`. */
export async function reverseSettlement(
  id: string,
  body: ReverseBody,
): Promise<unknown> {
  return adminApiFetch(`/admin/markets/${id}/reverse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** Force-settle a stuck Polymarket market (ADM-06). `POST /admin/markets/{id}/force-settle`. */
export async function forceSettle(
  id: string,
  body: ForceSettleBody,
): Promise<unknown> {
  return adminApiFetch(`/admin/markets/${id}/force-settle`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
