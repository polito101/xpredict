/**
 * Plan 08-03 — Admin user detail page (ADU-02, D-07).
 *
 * Server Component: fetches the user detail via the `fetchUserDetail` Server
 * Action (Bearer-forwarded admin_jwt) and hands it to the `UserDetailTabs`
 * client island (header + ban/unban dialogs + Profile/Wallet/Bets tabs). The
 * static "Back to users" link lives here in the server shell. If the fetch
 * fails (404 / expired session) we render the UI-SPEC error block instead of
 * crashing.
 *
 * Next.js 16: route `params` is async — it is awaited before use.
 *
 * Layout per UI-SPEC: `max-w-6xl mx-auto px-6 py-12`.
 */
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { UserDetailTabs } from "@/components/admin/user-detail-tabs";
import { fetchUserDetail } from "@/lib/admin-api";
import type { UserDetail } from "@/lib/admin-types";

export const dynamic = "force-dynamic";

export default async function AdminUserDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let user: UserDetail | null = null;
  try {
    user = await fetchUserDetail(id);
  } catch {
    user = null;
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <Link
        href="/admin/users"
        className="mb-8 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to users
      </Link>

      {user ? (
        <UserDetailTabs initialUser={user} />
      ) : (
        <div className="py-12 text-center">
          <p className="text-sm font-medium text-red-400">
            Failed to load data
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Something went wrong while loading this page. Please try again.
          </p>
        </div>
      )}
    </div>
  );
}
