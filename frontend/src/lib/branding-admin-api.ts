/**
 * Plan 10-03 — Branding admin API helper (Server Actions).
 *
 * Mirrors `admin-api.ts`: this module is `"use server"`, so the `admin_jwt`
 * HttpOnly cookie is read SERVER-SIDE via `next/headers > cookies()` and
 * forwarded as `Authorization: Bearer <token>` to FastAPI. The token NEVER
 * reaches client JS (threat T-10-11) — the client BrandingForm calls the
 * exported async `updateTenantConfig` directly; it cannot read the HttpOnly
 * cookie itself.
 *
 * Next constraint: a `"use server"` file may only export async functions, so
 * the shared types live in `./branding-types`.
 *
 * The PUT is multipart/form-data: `brand_name` + `primary_hex` +
 * `secondary_hex` + optional `logo` File. The backend status code is
 * preserved in the thrown Error message ("API error: 422") so the form can
 * branch on 422 and map server field errors to inline FormMessage (D-09 —
 * the server is authoritative on validation).
 *
 * BACKEND_URL is read from the server env (no `NEXT_PUBLIC_` prefix — it never
 * leaks into the client bundle), mirroring `admin-api.ts`.
 */
"use server";

import { cookies } from "next/headers";

import type { TenantConfigRead, BrandingUpdateInput } from "./branding-types";

function getBackendUrl(): string {
  return process.env.BACKEND_URL || "http://localhost:8000";
}

async function bearerHeader(): Promise<Record<string, string>> {
  const store = await cookies();
  const token = store.get("admin_jwt")?.value;
  if (!token) {
    throw new Error("Not authenticated");
  }
  return { Authorization: `Bearer ${token}` };
}

/**
 * `GET /api/v1/admin/tenant-config` — the current persisted branding config.
 * Bearer-forwarded, no-store (always the live row). Throws
 * `Error("API error: <status>")` on a non-2xx so the page can degrade.
 */
export async function fetchTenantConfig(): Promise<TenantConfigRead> {
  const auth = await bearerHeader();
  const res = await fetch(`${getBackendUrl()}/api/v1/admin/tenant-config`, {
    headers: auth,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  return res.json() as Promise<TenantConfigRead>;
}

/**
 * `PUT /api/v1/admin/tenant-config` — update the branding config as
 * multipart/form-data. The Bearer is forwarded server-side; the logo (when
 * present) crosses as a file part. We do NOT set Content-Type manually — fetch
 * derives the multipart boundary from the FormData body.
 *
 * On a non-2xx, throws `Error("API error: <status>")` so the form can branch
 * on 422 (server validation) and map field errors to inline FormMessage.
 */
export async function updateTenantConfig(
  input: BrandingUpdateInput,
): Promise<TenantConfigRead> {
  const auth = await bearerHeader();

  const body = new FormData();
  body.set("brand_name", input.brand_name);
  body.set("primary_hex", input.primary_hex);
  body.set("secondary_hex", input.secondary_hex);
  if (input.logo) {
    body.set("logo", input.logo);
  }

  const res = await fetch(`${getBackendUrl()}/api/v1/admin/tenant-config`, {
    method: "PUT",
    headers: auth, // do NOT set Content-Type — FormData sets the multipart boundary.
    body,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  return res.json() as Promise<TenantConfigRead>;
}
