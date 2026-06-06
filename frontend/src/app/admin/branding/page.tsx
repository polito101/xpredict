/**
 * Plan 10-03 — Admin branding page (ADD-05, D-07/D-09).
 *
 * Server Component: pre-fetches the current persisted branding config via the
 * `fetchTenantConfig` Server Action (Bearer-forwarded admin_jwt) and hands it
 * to the client-side `BrandingForm` so the form opens pre-filled with the live
 * brand name + palette + logo. If the initial load fails (e.g. the admin
 * session expired), it degrades to the XPredict defaults rather than crashing —
 * the form's own submit feedback covers subsequent write failures.
 *
 * NAV NOTE: this plan ships the ROUTE only. The admin-nav.tsx "Branding" link
 * pointing here is wired in Plan 10-04 (which owns admin-nav.tsx). The page is
 * reachable by direct URL in isolation.
 *
 * Layout per UI-SPEC: `mx-auto max-w-6xl px-6 py-12`, H1 "Branding" + subtext.
 */
import { BrandingForm } from "@/components/admin/branding-form";
import { fetchTenantConfig } from "@/lib/branding-admin-api";
import type { TenantConfigRead } from "@/lib/branding-types";

export const dynamic = "force-dynamic";

const DEFAULT_CONFIG: TenantConfigRead = {
  brand_name: "XPredict",
  primary_hex: "#4f46e5",
  secondary_hex: "#0ea5e9",
  logo_url: null,
};

export default async function AdminBrandingPage() {
  let initial: TenantConfigRead;
  try {
    initial = await fetchTenantConfig();
  } catch {
    initial = DEFAULT_CONFIG;
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <h1 className="text-3xl font-semibold tracking-tight">Branding</h1>
      <p className="mt-2 text-base text-muted-foreground">
        Customize how the platform looks to your players. Changes apply on the
        next page load — no redeploy.
      </p>
      <div className="mt-8">
        <BrandingForm initial={initial} />
      </div>
    </div>
  );
}
