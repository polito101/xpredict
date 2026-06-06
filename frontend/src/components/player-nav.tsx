/**
 * PlayerNav — primary navigation for the player surface.
 *
 * Client Component: uses `usePathname` to mark the active destination. Session
 * state is resolved server-side in the root layout (presence of the HttpOnly
 * `xpredict_session` cookie) and passed in as `isAuthenticated`; the optional
 * `playerName` (best-effort from `/auth/users/me`) drives the account affordance.
 * The cookie value never reaches client JS.
 *
 * Desktop shows a pill nav inline; mobile collapses the links behind a menu
 * button (the menu content renders only when open, so the desktop links remain
 * the single source of each label in the DOM).
 */
"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X } from "lucide-react";

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

function navLinkClass(active: boolean): string {
  return cn(
    "rounded-full px-3.5 py-2 text-sm font-medium transition-colors",
    active
      ? "bg-brand-primary/12 text-brand-primary"
      : "text-muted-foreground hover:bg-muted hover:text-foreground",
  );
}

export function PlayerNav({
  isAuthenticated,
  playerName,
}: {
  isAuthenticated: boolean;
  playerName?: string | null;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Desktop nav */}
      <nav
        className="hidden items-center gap-1 sm:flex"
        aria-label="Main navigation"
      >
        {DESTINATIONS.map(({ href, label }) => {
          const active = isActive(pathname, href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={navLinkClass(active)}
            >
              {label}
            </Link>
          );
        })}

        <span
          className="mx-1.5 h-5 w-px bg-border"
          aria-hidden="true"
        />

        {isAuthenticated ? (
          <div className="flex items-center gap-2">
            {playerName && (
              <Link
                href="/portfolio"
                className="flex items-center gap-2 rounded-full border border-border bg-muted/60 py-1 pl-1 pr-3 text-sm text-foreground transition-colors hover:border-border-strong"
              >
                <span className="grid h-6 w-6 place-items-center rounded-full bg-gradient-brand text-[0.65rem] font-semibold text-brand-primary-foreground">
                  {playerName.charAt(0).toUpperCase()}
                </span>
                <span className="max-w-[10ch] truncate">{playerName}</span>
              </Link>
            )}
            <form action={logoutAction}>
              <button
                type="submit"
                className="rounded-full px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                Log out
              </button>
            </form>
          </div>
        ) : (
          <div className="flex items-center gap-1.5">
            <Link href="/login" className={navLinkClass(false)}>
              Log in
            </Link>
            <Button asChild size="sm" className="rounded-full">
              <Link href="/register">Sign up</Link>
            </Button>
          </div>
        )}
      </nav>

      {/* Mobile menu button */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Close menu" : "Open menu"}
        aria-expanded={open}
        className="grid h-10 w-10 place-items-center rounded-full border border-border bg-muted/60 text-foreground transition-colors hover:border-border-strong sm:hidden"
      >
        {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
      </button>

      {/* Mobile menu sheet — rendered only when open (avoids duplicate labels). */}
      {open && (
        <div className="absolute inset-x-0 top-16 z-40 border-b border-border surface-glass sm:hidden">
          <nav
            className="mx-auto flex w-full max-w-6xl flex-col gap-1 px-4 py-3"
            aria-label="Mobile navigation"
          >
            {DESTINATIONS.map(({ href, label }) => {
              const active = isActive(pathname, href);
              return (
                <Link
                  key={href}
                  href={href}
                  onClick={() => setOpen(false)}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "rounded-xl px-4 py-3 text-base font-medium transition-colors",
                    active
                      ? "bg-brand-primary/12 text-brand-primary"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  {label}
                </Link>
              );
            })}
            <div className="my-1 h-px bg-border" />
            {isAuthenticated ? (
              <form action={logoutAction}>
                <button
                  type="submit"
                  className="w-full rounded-xl px-4 py-3 text-left text-base font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                >
                  Log out
                </button>
              </form>
            ) : (
              <div className="flex flex-col gap-2 pt-1">
                <Button asChild variant="outline" className="w-full">
                  <Link href="/login" onClick={() => setOpen(false)}>
                    Log in
                  </Link>
                </Button>
                <Button asChild className="w-full">
                  <Link href="/register" onClick={() => setOpen(false)}>
                    Sign up
                  </Link>
                </Button>
              </div>
            )}
          </nav>
        </div>
      )}
    </>
  );
}
