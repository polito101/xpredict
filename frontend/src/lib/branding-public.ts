/**
 * Plan 10-05 — public branding fetch helper (ADD-06 runtime theming, Slice B).
 *
 * Plain module (NOT a `"use server"` action): the player root layout reads the
 * PUBLIC `GET /branding/current` with no auth, so this mirrors the public-read
 * shape in `lib/api.ts` (`apiBase()` + `cache: "no-store"` + a typed throw on
 * `!res.ok`) rather than the Bearer-forwarding `admin-api.ts` shape.
 *
 * `cache: "no-store"` is the per-navigation freshness contract (SC#5): an
 * operator palette change in /admin/branding must re-skin the player on its
 * NEXT navigation with no rebuild/redeploy — so the branding payload is
 * fetched fresh on every render and never statically inlined.
 *
 * Security: the hexes returned here are server-validated `^#[0-9a-fA-F]{6}$`
 * BEFORE persist AND before the layout injects them into the `<style>` block
 * (Plan 10-01 / T-10-01). The layout treats them as opaque validated tokens.
 */

/** The public `/branding/current` payload (4 fields, no bytes — Pitfall 7). */
export interface BrandingPublic {
  brand_name: string;
  primary_hex: string;
  secondary_hex: string;
  logo_url: string | null;
}

/**
 * Indigo/sky safe-fallback palette. Applied by the root layout's try/catch when
 * `/branding/current` is unreachable so the player UI is never unbranded-broken
 * (UI-SPEC A-FALLBACK / accessibility guardrail #3 — both hexes are ≥4.5:1 on
 * white). Mirrors the `:root` defaults in `globals.css`.
 */
export const DEFAULT_BRANDING: BrandingPublic = {
  brand_name: "XPredict",
  primary_hex: "#4f46e5",
  secondary_hex: "#0ea5e9",
  logo_url: null,
};

/**
 * Resolves the backend base URL for the current execution context.
 *
 * Server-side (the root layout is a Server Component) reaches the backend over
 * the internal Docker network via `BACKEND_URL`; the browser must use the
 * host-reachable `NEXT_PUBLIC_API_URL`. Mirrors `lib/api.ts`'s `apiBase()`
 * verbatim (Phase 9 closeout: conflating the two broke client-side fetches
 * against the unresolvable Docker-internal hostname).
 */
function apiBase(): string {
  if (typeof window === "undefined") {
    return (
      process.env.BACKEND_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "http://localhost:8000"
    );
  }
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

/**
 * Fetches the public branding config from the backend. Uses `cache: "no-store"`
 * so a re-skin applies on the player's next navigation (SC#5). Throws on a
 * non-2xx response — the caller (root layout) catches it and applies
 * `DEFAULT_BRANDING`.
 */
export async function fetchBrandingPublic(): Promise<BrandingPublic> {
  const res = await fetch(`${apiBase()}/branding/current`, {
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch branding: ${res.status}`);
  }

  return res.json() as Promise<BrandingPublic>;
}
