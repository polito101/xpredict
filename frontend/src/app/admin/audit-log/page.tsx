/**
 * Plan 08-03 — Admin audit log viewer page (ADD-04, D-11/D-12/D-13).
 *
 * Server Component: does the initial page-1 fetch (page_size = 50, D-11) and
 * loads the event-type taxonomy for the filter dropdown (D-13) via the
 * `fetchAuditLog` / `fetchAuditEventTypes` Server Actions (Bearer-forwarded
 * admin_jwt), then hands both to the client-side `AuditLogTable`. If the
 * initial load fails (e.g. the admin session expired) it degrades to an empty
 * table rather than crashing — the table's own error state covers subsequent
 * refetch failures.
 *
 * Layout per UI-SPEC: `max-w-6xl mx-auto px-6 py-12`, heading "Audit Log".
 * Read-only surface — no mutation controls anywhere (D-11).
 */
import { AuditLogTable } from "@/components/admin/audit-log-table";
import { fetchAuditLog, fetchAuditEventTypes } from "@/lib/admin-api";
import type { AuditLogItem, PaginatedResponse } from "@/lib/admin-types";

export const dynamic = "force-dynamic";

export default async function AdminAuditLogPage() {
  let initialData: PaginatedResponse<AuditLogItem>;
  let eventTypes: string[];
  try {
    [initialData, eventTypes] = await Promise.all([
      fetchAuditLog({ page: 1, page_size: 50 }),
      fetchAuditEventTypes(),
    ]);
  } catch {
    initialData = { items: [], total: 0, page: 1, page_size: 50, pages: 1 };
    eventTypes = [];
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <h1 className="mb-8 text-xl font-semibold tracking-tight">Audit Log</h1>
      <AuditLogTable initialData={initialData} eventTypes={eventTypes} />
    </div>
  );
}
