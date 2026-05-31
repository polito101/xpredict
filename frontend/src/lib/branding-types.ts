/**
 * Plan 10-03 — Branding admin shared types.
 *
 * These live OUTSIDE `branding-admin-api.ts` because Next's `"use server"`
 * files may only export async functions (mirrors the `admin-api.ts` /
 * `admin-types.ts` split). Client components (the BrandingForm) and the
 * Server Action both import the types from here.
 *
 * Shapes are transcribed from the verified Plan 10-01 backend contract
 * (`backend/app/branding/schemas.py`): `GET /api/v1/admin/tenant-config`
 * returns `TenantConfigRead`; `PUT` accepts a multipart body
 * (`brand_name` + 2 hexes + optional `logo` file).
 */

/** Shape returned by `GET /api/v1/admin/tenant-config` (no logo bytes). */
export interface TenantConfigRead {
  brand_name: string;
  primary_hex: string;
  secondary_hex: string;
  /** `/branding/logo` URL when a logo is set, else null (no bytes inlined). */
  logo_url: string | null;
}

/**
 * Input to `updateTenantConfig` — the multipart PUT payload. The hexes are
 * client-validated for UX only; the server (Plan 10-01) is authoritative
 * (`^#[0-9a-fA-F]{6}$` → 422). `logo` is optional: omit it to leave an
 * existing logo untouched (the backend ignores an empty file part).
 */
export interface BrandingUpdateInput {
  brand_name: string;
  primary_hex: string;
  secondary_hex: string;
  /** Optional new logo file; omitted = no logo change. */
  logo?: File;
}
