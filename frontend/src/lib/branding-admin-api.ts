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
 * `secondary_hex` + optional `logo` File. On a non-2xx the helper throws an
 * Error whose `message` is a JSON-encoded `BrandingApiError` carrying the real
 * HTTP `status` plus, for a 422, the per-field validation errors parsed from
 * FastAPI's structured `detail` (`exc.errors()` with `loc`). This lets the
 * form map a 422 to the FIELD that actually failed (brand_name vs a hex)
 * instead of blaming the colors, and treat 401/403 as a session problem rather
 * than "invalid fields" (WR-04 / D-09 — the server is authoritative).
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

// Map a FastAPI/Pydantic field name (the last non-"body" segment of `loc`) to
// the form field. The PUT body validates brand_name + the two hexes
// (TenantConfigUpdate). Anything else stays unmapped → the form shows a generic
// message rather than a misleading per-field one.
const _FORM_FIELDS = new Set(["brand_name", "primary_hex", "secondary_hex"]);

interface FastApiErrorItem {
  loc?: unknown[];
  msg?: string;
}

/**
 * Parse FastAPI's 422 `detail` (an array of `{loc, msg}`) into a compact
 * `{field: message}` map keyed by the offending form field. Returns an empty
 * object when the body is not the expected structured shape.
 */
function parseFieldErrors(detail: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (!Array.isArray(detail)) {
    return out;
  }
  for (const item of detail as FastApiErrorItem[]) {
    const loc = Array.isArray(item?.loc) ? item.loc : [];
    // FastAPI prefixes body-field locs with "body"; take the last string seg.
    const field = [...loc].reverse().find((s) => typeof s === "string") as
      | string
      | undefined;
    if (field && _FORM_FIELDS.has(field) && typeof item.msg === "string") {
      out[field] = item.msg;
    }
  }
  return out;
}

/**
 * Build the structured Error thrown on a non-2xx. The `message` is JSON so the
 * client form can recover `status` + `fieldErrors` across the Server Action
 * boundary (where Error objects are otherwise opaque). Falls back to a bare
 * status payload when the response body is not JSON.
 */
async function buildApiError(res: Response): Promise<Error> {
  let fieldErrors: Record<string, string> = {};
  if (res.status === 422) {
    try {
      const body = (await res.json()) as { detail?: unknown };
      fieldErrors = parseFieldErrors(body?.detail);
    } catch {
      // Non-JSON / empty 422 body — leave fieldErrors empty.
    }
  }
  return new Error(
    JSON.stringify({ kind: "branding_api_error", status: res.status, fieldErrors }),
  );
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
 * Bearer-forwarded, no-store (always the live row). Throws a structured
 * `BrandingApiError` (JSON message carrying the real `status`) on a non-2xx so
 * the page can degrade.
 */
export async function fetchTenantConfig(): Promise<TenantConfigRead> {
  const auth = await bearerHeader();
  const res = await fetch(`${getBackendUrl()}/api/v1/admin/tenant-config`, {
    headers: auth,
    cache: "no-store",
  });
  if (!res.ok) {
    throw await buildApiError(res);
  }
  return res.json() as Promise<TenantConfigRead>;
}

/**
 * `PUT /api/v1/admin/tenant-config` — update the branding config as
 * multipart/form-data. The Bearer is forwarded server-side; the logo (when
 * present) crosses as a file part. We do NOT set Content-Type manually — fetch
 * derives the multipart boundary from the FormData body.
 *
 * On a non-2xx, throws a structured `BrandingApiError` (JSON message with the
 * real `status` and, for a 422, the per-field validation messages) so the form
 * can map a field-level rejection to the field that actually failed and treat
 * 401/403 as a session problem.
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
    throw await buildApiError(res);
  }
  return res.json() as Promise<TenantConfigRead>;
}
