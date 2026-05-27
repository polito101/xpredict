/**
 * Plan 02-05 Task 2 — Admin section layout.
 *
 * Wraps every `/admin/*` route (including `/admin/login`) with a top
 * navigation bar that visually distinguishes the admin surface from
 * the player UI. The nav is placeholder-only for Phase 2; Phase 8
 * (Admin CRM) will populate it with real links to users / markets /
 * audit log views.
 *
 * Server Component (no `"use client"`) — purely structural; reads
 * nothing from cookies or session state.
 *
 * Trust boundary: the layout itself does NOT enforce authentication.
 * The Edge middleware (frontend/src/middleware.ts) handles optimistic
 * gate; FastAPI's `current_active_admin` (Plan 02-03) is the
 * authoritative gate on every `/admin/*` API call.
 */
import Link from "next/link";

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen flex flex-col bg-zinc-50 dark:bg-zinc-950">
      <nav className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <Link
            href="/admin"
            className="text-lg font-semibold tracking-tight text-zinc-900 dark:text-zinc-50"
          >
            XPredict Admin
          </Link>
          <div className="flex items-center gap-4 text-sm">
            {/* Phase 8 will replace these placeholders with real CRM links. */}
            <span className="text-zinc-400">Users</span>
            <span className="text-zinc-400">Markets</span>
            <span className="text-zinc-400">Audit log</span>
            <Link
              href="/admin/logout"
              className="text-zinc-600 underline hover:text-zinc-900 dark:text-zinc-300 dark:hover:text-zinc-50"
            >
              Log out
            </Link>
          </div>
        </div>
      </nav>
      <main className="flex-1">{children}</main>
    </div>
  );
}
