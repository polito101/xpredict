/**
 * Plan 10-04 — Admin KPI dashboard landing (ADD-01..03, replaces the Phase
 * 02-05 placeholder).
 *
 * After a successful `adminLoginAction`, the EXISTING `redirect("/admin")` in
 * lib/auth.ts lands the operator HERE — and because this page IS the dashboard
 * now, they see the five KPI cards + the 30-day volume chart (the operator
 * 5-second health pulse), not the old placeholder. This plan adds NO new
 * redirect; it makes /admin BE the dashboard so the existing post-login
 * redirect resolves to it (SC#1).
 *
 * Server Component: `await`s the initial KPI payload via the `fetchKpis`
 * "use server" action (Bearer-forwarded admin_jwt). If the initial load fails
 * (e.g. the admin session expired), it degrades to the KPI-load-error copy
 * rather than crashing (mirrors users/page.tsx try/catch). The DAU window
 * toggle is interactive, so the client `KpiDashboard` owns the refetch.
 */
import { KpiDashboard } from "@/components/admin/kpi-dashboard";
import { AdminDefaultRoute } from "@/components/admin/admin-default-route";
import { fetchKpis } from "@/lib/kpi-api";
import type { KpiResponse } from "@/lib/kpi-types";

export const dynamic = "force-dynamic";

export default async function AdminHomePage() {
  let kpis: KpiResponse | null = null;
  try {
    kpis = await fetchKpis("24h");
  } catch {
    kpis = null;
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <h1 className="text-3xl font-semibold tracking-tight">Dashboard</h1>
      <p className="mt-2 text-muted-foreground">
        Your platform at a glance.
      </p>

      {kpis === null ? (
        <p className="mt-8 text-sm text-muted-foreground">
          Couldn&apos;t load dashboard metrics. Refresh the page to try again.
        </p>
      ) : (
        <KpiDashboard initial={kpis} />
      )}

      <AdminDefaultRoute />
    </div>
  );
}
