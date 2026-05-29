/**
 * Plan 08-03 — Admin CRM shared types.
 *
 * These type definitions live OUTSIDE `admin-api.ts` because Next's
 * `"use server"` files may only export async functions (mirrors the
 * `auth.ts` / `auth-schemas.ts` split). Client components and Server
 * Actions both import the types from here.
 *
 * Shapes are transcribed verbatim from the verified backend contracts
 * (`backend/app/admin/schemas.py`, `core/audit/schemas.py`). Base path is
 * `/api/v1/admin`.
 *
 * MONEY DISCIPLINE (CLAUDE.md hard constraint): balance / amount / stake /
 * pnl arrive from the backend as STRINGS (NUMERIC(18,4) serialized via
 * `Decimal -> str`). They are typed as `string` here and rendered verbatim —
 * NEVER `parseFloat` / `Number()` (floats lose precision).
 */

/** Generic paginated envelope returned by every admin list endpoint. */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export type UserStatus = "active" | "banned";

/** Row shape from `GET /users`. `last_activity` is list-only (null on detail). */
export interface UserListItem {
  id: string;
  email: string;
  display_name: string | null;
  banned_at: string | null;
  created_at: string;
  last_activity: string | null;
  balance: string; // money — string, never a float
  status: UserStatus;
}

/**
 * Shape from `GET /users/{id}`. Extends UserListItem with verification +
 * aggregate counts. NOTE (verified against live source): on the detail
 * endpoint `last_activity` is always null (list-only) and `email_verified_at`
 * is always null — drive the "Verified" display off the `is_verified`
 * boolean, not off `email_verified_at`.
 */
export interface UserDetail extends UserListItem {
  is_verified: boolean;
  email_verified_at: string | null;
  transaction_count: number;
  bet_count: number;
}

/** Row shape from `GET /users/{id}/transactions`. Field is `kind`. */
export interface UserTransactionItem {
  id: string;
  kind: string;
  amount: string; // money — string
  created_at: string;
  reason: string | null;
}

/** Row shape from `GET /users/{id}/bets`. */
export interface UserBetItem {
  id: string;
  market_question: string;
  outcome_label: string;
  stake: string; // money — string
  status: string;
  pnl: string | null; // money — string or null (open bets)
  created_at: string;
}

/** Row shape from `GET /audit-log`. */
export interface AuditLogItem {
  id: string;
  occurred_at: string;
  event_type: string;
  actor: string;
  payload: Record<string, unknown>;
  ip: string | null;
}

/** Query params for the user list / export-users endpoints. */
export interface UserListParams {
  page?: number;
  page_size?: number;
  search?: string;
  status?: UserStatus | "";
  signup_after?: string;
  signup_before?: string;
  sort_by?: string;
  sort_order?: "asc" | "desc";
}

/** Query params for the audit-log endpoint. */
export interface AuditLogParams {
  page?: number;
  page_size?: number;
  event_type?: string;
  actor?: string;
  date_from?: string;
  date_to?: string;
}
