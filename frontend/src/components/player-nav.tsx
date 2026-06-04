/**
 * PlayerNav — primary navigation for the player surface (v1.1 Fase C).
 *
 * Client Component: uses `usePathname` to mark the active destination. Session
 * state is resolved server-side in the root layout (presence of the HttpOnly
 * `xpredict_session` cookie) and passed in as `isAuthenticated` — the cookie
 * value never reaches client JS.
 */
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { logoutAction } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const DESTINATIONS = [
  { href: "/", label: "Markets" },
  { href: "/wallet", label: "Wallet" },
  { href: "/portfolio", label: "Portfolio" },
] as const;

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

export function PlayerNav({ isAuthenticated }: { isAuthenticated: boolean }) {
  const pathname = usePathname();

  return (
    <nav className="flex items-center gap-0.5 sm:gap-1" aria-label="Main navigation">
      {DESTINATIONS.map(({ href, label }) => {
        const active = isActive(pathname, href);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "rounded-md px-2.5 py-2 text-sm font-medium transition-colors sm:px-3",
              active
                ? "text-brand-primary"
                : "text-zinc-600 hover:text-zinc-900",
            )}
          >
            {label}
          </Link>
        );
      })}

      <span className="mx-1 h-5 w-px bg-zinc-200" aria-hidden="true" />

      {isAuthenticated ? (
        <form action={logoutAction}>
          <button
            type="submit"
            className="rounded-md px-2.5 py-2 text-sm font-medium text-zinc-600 transition-colors hover:text-zinc-900 sm:px-3"
          >
            Log out
          </button>
        </form>
      ) : (
        <div className="flex items-center gap-1">
          <Link
            href="/login"
            className="rounded-md px-2.5 py-2 text-sm font-medium text-zinc-600 transition-colors hover:text-zinc-900 sm:px-3"
          >
            Log in
          </Link>
          <Button asChild size="sm">
            <Link href="/register">Sign up</Link>
          </Button>
        </div>
      )}
    </nav>
  );
}
