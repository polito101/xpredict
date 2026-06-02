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

import { AdminNav } from "@/components/admin/admin-nav";

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
          {/* Phase 8: active CRM links (Users / Audit log) + Markets placeholder. */}
          <AdminNav />
        </div>
      </nav>
      <main className="flex-1">{children}</main>
      <footer className="border-t border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="mx-auto flex max-w-6xl flex-col gap-1 px-6 py-4 text-xs text-zinc-500 dark:text-zinc-400 sm:flex-row sm:items-center sm:justify-between">
          <nav className="flex flex-wrap gap-x-4 gap-y-1">
            <Link
              href="https://github.com/polito101/xpredict/blob/main/docs/terms-of-service.md"
              className="hover:text-zinc-700 dark:hover:text-zinc-200"
            >
              Terms of Service
            </Link>
            <Link
              href="https://github.com/polito101/xpredict/blob/main/docs/regulatory.md"
              className="hover:text-zinc-700 dark:hover:text-zinc-200"
            >
              Token policy
            </Link>
          </nav>
          <p>Play-money tokens have no monetary value.</p>
        </div>
      </footer>
    </div>
  );
}
