/**
 * Plan 08-03 — Admin user list page (ADU-01, D-06).
 *
 * Server Component: does the initial page-1 fetch via the `fetchUsers` Server
 * Action (Bearer-forwarded admin_jwt) and hands the data to the client-side
 * `UsersDataTable`. If the initial load fails (e.g. the admin session expired),
 * it degrades to an empty table rather than crashing — the table's own error
 * state covers subsequent refetch failures.
 *
 * Layout per UI-SPEC: `max-w-6xl mx-auto px-6 py-12`, heading "Users".
 */
import { UsersDataTable } from "@/components/admin/users-data-table";
import { fetchUsers } from "@/lib/admin-api";
import type { PaginatedResponse, UserListItem } from "@/lib/admin-types";

export const dynamic = "force-dynamic";

export default async function AdminUsersPage() {
  let initialData: PaginatedResponse<UserListItem>;
  try {
    initialData = await fetchUsers({
      page: 1,
      page_size: 20,
      sort_by: "created_at",
      sort_order: "desc",
    });
  } catch {
    initialData = { items: [], total: 0, page: 1, page_size: 20, pages: 1 };
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <h1 className="mb-8 text-xl font-semibold tracking-tight">Users</h1>
      <UsersDataTable initialData={initialData} />
    </div>
  );
}
