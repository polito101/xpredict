/**
 * Plan 08-03 — Admin CRM API helper (Server Actions).
 *
 * Every admin API call from the frontend funnels through here. This module is
 * `"use server"`, so the `admin_jwt` HttpOnly cookie is read SERVER-SIDE via
 * `next/headers > cookies()` and forwarded as `Authorization: Bearer <token>`
 * to FastAPI. The token NEVER reaches client JS (threat T-08-10 / T-08-12 —
 * see <threat_model> in 08-03-PLAN.md). Client components call these exported
 * async functions directly; they cannot read the HttpOnly cookie themselves.
 *
 * Next constraint: a `"use server"` file may only export async functions, so
 * all shared types live in `./admin-types`.
 *
 * BACKEND_URL is read from the server env (no `NEXT_PUBLIC_` prefix — it never
 * leaks into the client bundle), mirroring `lib/auth.ts`.
 */
"use server";

import { cookies } from "next/headers";

import type {
  PaginatedResponse,
  UserListItem,
  UserDetail,
  UserTransactionItem,
  UserBetItem,
  AuditLogItem,
  UserListParams,
  AuditLogParams,
} from "./admin-types";
import { buildQuery, buildUsersQuery } from "./admin-query";

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
 * code is preserved in the message so callers can branch on, e.g., 403).
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

/**
 * Export fetch — same Bearer forwarding, but returns the raw CSV text + the
 * suggested filename parsed from Content-Disposition. The client component
 * turns the text into a Blob and triggers the download (a raw Response cannot
 * be returned across the Server Action boundary, so we return a plain object).
 */
export async function adminApiExport(
  path: string,
): Promise<{ csv: string; filename: string }> {
  const auth = await bearerHeader();
  const res = await fetch(`${getBackendUrl()}${path}`, {
    headers: auth,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Export error: ${res.status}`);
  }
  const csv = await res.text();
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = disposition.match(/filename="?([^"]+)"?/i);
  const filename = match ? match[1] : "export.csv";
  return { csv, filename };
}

// ---------------------------------------------------------------------------
// Typed query builders + endpoint wrappers
// ---------------------------------------------------------------------------

// buildQuery + buildUsersQuery moved to ./admin-query (sync, client-usable — WR-02).

export async function fetchUsers(
  params: UserListParams,
): Promise<PaginatedResponse<UserListItem>> {
  const qs = buildUsersQuery(params);
  return adminApiFetch<PaginatedResponse<UserListItem>>(
    `/api/v1/admin/users${qs}`,
  );
}

export async function fetchUserDetail(id: string): Promise<UserDetail> {
  return adminApiFetch<UserDetail>(`/api/v1/admin/users/${id}`);
}

export async function fetchUserTransactions(
  id: string,
  page: number,
  pageSize = 20,
): Promise<PaginatedResponse<UserTransactionItem>> {
  const qs = buildQuery({ page, page_size: pageSize });
  return adminApiFetch<PaginatedResponse<UserTransactionItem>>(
    `/api/v1/admin/users/${id}/transactions${qs}`,
  );
}

export async function fetchUserBets(
  id: string,
  page: number,
  pageSize = 20,
): Promise<PaginatedResponse<UserBetItem>> {
  const qs = buildQuery({ page, page_size: pageSize });
  return adminApiFetch<PaginatedResponse<UserBetItem>>(
    `/api/v1/admin/users/${id}/bets${qs}`,
  );
}

/** Ban a user. `reason` is REQUIRED (backend min_length=1, extra="forbid"). */
export async function banUser(
  id: string,
  reason: string,
): Promise<UserDetail> {
  return adminApiFetch<UserDetail>(`/api/v1/admin/users/${id}/ban`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
}

/** Unban a user. `reason` is OPTIONAL (sent only when provided). */
export async function unbanUser(
  id: string,
  reason?: string,
): Promise<UserDetail> {
  const payload =
    reason && reason.trim().length > 0 ? { reason } : {};
  return adminApiFetch<UserDetail>(`/api/v1/admin/users/${id}/unban`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

/**
 * Recharge a user's wallet (Phase 3 primitive). Requires a fresh
 * `Idempotency-Key` (UUID v4) per submission — the caller generates it and
 * passes it in so a retry of the SAME logical submit reuses the key
 * (threat T-08-11 double-submit mitigation). Returns 403 if the target user
 * is banned (the form is disabled in that state, but the backend is
 * authoritative).
 */
export async function rechargeWallet(
  userId: string,
  amount: string,
  reason: string,
  idempotencyKey: string,
): Promise<unknown> {
  return adminApiFetch(`/admin/wallets/${userId}/recharge`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify({ amount, reason }),
  });
}

export async function fetchAuditLog(
  params: AuditLogParams,
): Promise<PaginatedResponse<AuditLogItem>> {
  const qs = buildQuery({
    page: params.page,
    page_size: params.page_size ?? 50,
    event_type: params.event_type,
    actor: params.actor,
    date_from: params.date_from,
    date_to: params.date_to,
  });
  return adminApiFetch<PaginatedResponse<AuditLogItem>>(
    `/api/v1/admin/audit-log${qs}`,
  );
}

export async function fetchAuditEventTypes(): Promise<string[]> {
  return adminApiFetch<string[]>(`/api/v1/admin/audit-log/event-types`);
}
