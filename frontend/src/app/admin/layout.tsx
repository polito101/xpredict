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
import { LogoMark } from "@/components/brand/logo-mark";

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen flex flex-col bg-background">
      <header className="sticky top-0 z-40 border-b border-border/70 surface-glass">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3">
          <Link
            href="/admin"
            className="group inline-flex items-center gap-2.5 font-display text-base font-semibold tracking-tight text-foreground"
          >
            <LogoMark className="h-7 w-7 transition-transform duration-300 group-hover:scale-105" />
            <span>
              <span className="text-gradient-brand">X</span>Prediction
            </span>
            <span className="rounded-full border border-border bg-muted px-2 py-0.5 text-[0.65rem] font-medium uppercase tracking-wide text-muted-foreground">
              Admin
            </span>
          </Link>
          <AdminNav />
        </div>
      </header>
      <main className="flex-1">{children}</main>
      <footer className="border-t border-border bg-card">
        <div className="mx-auto flex max-w-6xl flex-col gap-1 px-6 py-4 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <nav className="flex flex-wrap gap-x-4 gap-y-1">
            <Link
              href="https://github.com/polito101/xpredict/blob/main/docs/terms-of-service.md"
              className="hover:text-foreground"
            >
              Terms of Service
            </Link>
            <Link
              href="https://github.com/polito101/xpredict/blob/main/docs/regulatory.md"
              className="hover:text-foreground"
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
