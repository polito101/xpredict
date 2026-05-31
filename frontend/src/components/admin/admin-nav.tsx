/**
 * Plan 08-03 — Admin top-nav links (client component).
 *
 * Extracted from `app/admin/layout.tsx` (which stays a Server Component) so it
 * can use `usePathname()` to highlight the active link per UI-SPEC §Layout
 * Contract. "Users" and "Audit log" are real links; "Markets" stays a disabled
 * placeholder (Phase 10 / deferred).
 *
 * Active:   text-zinc-900 font-semibold underline underline-offset-4 (dark: zinc-50)
 * Inactive: text-zinc-500 hover:text-zinc-900 (dark: zinc-400 hover:zinc-50)
 */
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const LINKS: { href: string; label: string }[] = [
  { href: "/admin/users", label: "Users" },
  { href: "/admin/audit-log", label: "Audit log" },
];

export function AdminNav() {
  const pathname = usePathname();

  return (
    <div className="flex items-center gap-4 text-sm">
      {LINKS.map((link) => {
        const active =
          pathname === link.href || pathname.startsWith(`${link.href}/`);
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              active
                ? "font-semibold text-zinc-900 underline underline-offset-4 dark:text-zinc-50"
                : "text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-50",
            )}
          >
            {link.label}
          </Link>
        );
      })}
      {/* Markets stays a disabled placeholder (Phase 10 / deferred). */}
      <span className="cursor-default text-zinc-400">Markets</span>
      <Link
        href="/admin/logout"
        className="text-zinc-600 underline hover:text-zinc-900 dark:text-zinc-300 dark:hover:text-zinc-50"
      >
        Log out
      </Link>
    </div>
  );
}
