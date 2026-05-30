/**
 * Plan 08-03 — admin query-string builders.
 *
 * Pure, synchronous helpers (NO "use server"): they only assemble a query
 * string and must be callable from Client Components without crossing the
 * Server Action boundary. `admin-api.ts` ("use server") imports these for its
 * own fetch URLs; `export-csv-button.tsx` (client) imports `buildUsersQuery`
 * directly so building the CSV export URL costs zero server round-trips
 * (code-review WR-02).
 */
import type { UserListParams } from "./admin-types";

/** Build a `?a=b&c=d` query string, skipping undefined/null/"" values. */
export function buildQuery(params: Record<string, unknown>): string {
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    sp.set(key, String(value));
  }
  const qs = sp.toString();
  return qs ? `?${qs}` : "";
}

/** Build the `/users` query string (shared by the list fetch + the CSV export). */
export function buildUsersQuery(params: UserListParams): string {
  return buildQuery({
    page: params.page,
    page_size: params.page_size,
    search: params.search,
    status: params.status,
    signup_after: params.signup_after,
    signup_before: params.signup_before,
    sort_by: params.sort_by,
    sort_order: params.sort_order,
  });
}
