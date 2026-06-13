/**
 * Plan 10-04 — Admin KPI dashboard API helper (Server Action).
 *
 * `"use server"` module: the `admin_jwt` HttpOnly cookie is read SERVER-SIDE
 * via `next/headers > cookies()` and forwarded as `Authorization: Bearer
 * <token>` to FastAPI. The token NEVER reaches client JS (threat T-10-15) —
 * the client `KpiDashboard` calls the exported `fetchKpis` async action and
 * cannot read the HttpOnly cookie itself. This reuses the proven pattern from
 * admin-api.ts (Plan 08-03 / RESEARCH A6).
 *
 * Next constraint: a `"use server"` file may only export async functions, so
 * the shared types live in `./kpi-types`.
 *
 * BACKEND_URL is read from the server env (no `NEXT_PUBLIC_` prefix — it never
 * leaks into the client bundle), mirroring admin-api.ts / lib/auth.ts.
 */
"use server";

import { cookies } from "next/headers";

import type { KpiResponse, KpiWindow } from "./kpi-types";
import { getBackendUrl } from "./config";

async function bearerHeader(): Promise<Record<string, string>> {
  const store = await cookies();
  const token = store.get("admin_jwt")?.value;
  if (!token) {
    throw new Error("Not authenticated");
  }
  return { Authorization: `Bearer ${token}` };
}

/**
 * Fetch the admin KPI dashboard payload for the given window.
 *
 * Forwards the admin Bearer to `GET /api/v1/admin/dashboard/kpis?window=` and
 * returns the five cards + the 30-day volume buckets. Throws
 * `Error("API error: <status>")` on a non-2xx response (status preserved so a
 * caller can branch on 401/403). `cache: "no-store"` — KPIs are live.
 */
export async function fetchKpis(window: KpiWindow): Promise<KpiResponse> {
  const auth = await bearerHeader();
  const res = await fetch(
    `${getBackendUrl()}/api/v1/admin/dashboard/kpis?window=${window}`,
    {
      headers: auth,
      cache: "no-store",
    },
  );
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  return res.json() as Promise<KpiResponse>;
}
