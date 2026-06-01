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

/**
 * The decoded shape of a non-2xx thrown by the branding Server Actions
 * (`branding-admin-api.ts`). `status` is the real backend HTTP status;
 * `fieldErrors` maps a form field (`brand_name` | `primary_hex` |
 * `secondary_hex`) to its server validation message for a 422 (WR-04).
 */
export interface BrandingApiError {
  status: number | null;
  fieldErrors: Record<string, string>;
}

/**
 * Decode a thrown branding error back into its `{status, fieldErrors}` shape.
 *
 * The Server Action throws an Error whose `message` is JSON
 * (`{kind:"branding_api_error", status, fieldErrors}`). This pure helper lives
 * here (not in the `"use server"` file, which may only export async functions)
 * so the client form can recover the structured info. Falls back to parsing the
 * legacy `"API error: <status>"` string, then to a null/empty result, so an
 * unexpected error never crashes the handler.
 */
export function parseBrandingApiError(err: unknown): BrandingApiError {
  const message = err instanceof Error ? err.message : String(err ?? "");
  try {
    const parsed = JSON.parse(message) as Partial<BrandingApiError> & {
      kind?: string;
    };
    if (parsed && parsed.kind === "branding_api_error") {
      return {
        status: typeof parsed.status === "number" ? parsed.status : null,
        fieldErrors:
          parsed.fieldErrors && typeof parsed.fieldErrors === "object"
            ? parsed.fieldErrors
            : {},
      };
    }
  } catch {
    // Not JSON — fall through to the legacy string form.
  }
  const legacy = /(\d{3})/.exec(message);
  return {
    status: legacy ? Number(legacy[1]) : null,
    fieldErrors: {},
  };
}
