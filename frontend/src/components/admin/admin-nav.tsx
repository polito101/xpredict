/**
 * Plan 08-03 — Admin top-nav links (client component).
 * Plan 10-04 — added the leading "Dashboard" link (/admin) and "Branding"
 *   (/admin/branding); this plan OWNS this file.
 *
 * Extracted from `app/admin/layout.tsx` (which stays a Server Component) so it
 * can use `usePathname()` to highlight the active link per UI-SPEC §Layout
 * Contract. "Dashboard", "Users", "Audit log", "Branding" and "Markets" are all
 * real links (Plan 12-05 enabled "Markets" → /admin/markets, BLOCKER-3).
 *
 * "Log out" is NOT a link — it submits the `adminLogoutAction` Server Action
 * (revokes the admin Bearer via POST /admin/auth/logout + clears the admin_jwt
 * cookie, then redirects to /admin/login), mirroring how player-nav posts
 * `logoutAction`. There is deliberately no `/admin/logout` route.
 *
 * Active:   text-foreground font-semibold underline underline-offset-4 (dark: zinc-50)
 * Inactive: text-muted-foreground hover:text-foreground (dark: zinc-400 hover:zinc-50)
 *
 * `/admin` (Dashboard) uses an EXACT-match active check (`pathname === "/admin"`)
 * — a `startsWith("/admin/")` would mark Dashboard active on every admin
 * sub-route. The other links keep the prefix (startsWith) behavior.
 */
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { adminLogoutAction } from "@/lib/auth";
import { cn } from "@/lib/utils";

const LINKS: { href: string; label: string; exact?: boolean }[] = [
  { href: "/admin", label: "Dashboard", exact: true },
  { href: "/admin/users", label: "Users" },
  { href: "/admin/markets", label: "Markets" },
  { href: "/admin/events", label: "Events" },
  { href: "/admin/audit-log", label: "Audit log" },
  { href: "/admin/branding", label: "Branding" },
];

export function AdminNav() {
  const pathname = usePathname();

  return (
    <div className="flex items-center gap-0.5 text-sm">
      {LINKS.map((link) => {
        const active = link.exact
          ? pathname === "/admin"
          : pathname === link.href || pathname.startsWith(`${link.href}/`);
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "hidden rounded-full px-3 py-1.5 font-medium transition-colors md:inline-block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
              active
                ? "bg-brand-primary/15 font-semibold text-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            {link.label}
          </Link>
        );
      })}
      <span className="mx-1.5 hidden h-5 w-px bg-border md:inline-block" aria-hidden="true" />
      <form action={adminLogoutAction}>
        <button
          type="submit"
          className="rounded-full px-3 py-1.5 font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          Log out
        </button>
      </form>
    </div>
  );
}
