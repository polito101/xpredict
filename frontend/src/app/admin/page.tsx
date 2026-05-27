/**
 * Plan 02-05 Task 2 — Admin landing page (placeholder).
 *
 * After a successful `adminLoginAction`, the user lands here. Phase 10
 * (ADD-01..03) replaces this content with the KPI dashboard (volume
 * staked, active users, house P&L). Phase 8 adds the user CRM, market
 * management, and audit log viewer that the layout nav points at.
 *
 * Until then, this server component simply confirms the operator
 * reached the authenticated admin shell — the value of the page is that
 * it RENDERS WITHOUT CRASHING when the middleware lets the request in,
 * fulfilling success criteria #4.
 */
export default function AdminHomePage() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <h1 className="text-3xl font-semibold tracking-tight">Admin dashboard</h1>
      <p className="mt-4 text-zinc-600 dark:text-zinc-400">
        KPI dashboard arrives in Phase 10. Phase 8 will add the user CRM,
        market management, and audit log viewer.
      </p>
    </div>
  );
}
