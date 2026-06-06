/**
 * PlayerNav — primary navigation for the player surface.
 *
 * Client Component: uses `usePathname` to mark the active destination. Session
 * state is resolved server-side in the root layout (presence of the HttpOnly
 * `xpredict_session` cookie) and passed in as `isAuthenticated`; the optional
 * `playerName` (best-effort from `/auth/users/me`) drives the account affordance.
 * The cookie value never reaches client JS.
 *
 * Phase 19 — landing/app split: the public landing (`/`) is brand-only, and the
 * app (markets, wallet, portfolio) lives behind authentication. So the app
 * destinations show ONLY when authenticated; a logged-out visitor sees just
 * Log in / Sign up. Desktop shows the nav inline; logged-in mobile collapses the
 * destinations behind a menu button (rendered only when open, so the desktop
 * links remain the single source of each label in the DOM).
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
  { href: "/markets", label: "Markets" },
  { href: "/live", label: "Live" },
  { href: "/wallet", label: "Wallet" },
  { href: "/portfolio", label: "Portfolio" },
] as const;

function isActive(pathname: string, href: string): boolean {
  if (href === "/markets") {
    return pathname.startsWith("/markets") || pathname.startsWith("/events");
  }
  return pathname.startsWith(href);
}

const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background";

function navLinkClass(active: boolean): string {
  return cn(
    "rounded-full px-3.5 py-2 text-sm font-medium transition-colors",
    FOCUS_RING,
    active
      ? "bg-brand-primary/15 font-semibold text-foreground"
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

  // Logged-out: the landing chrome — just Log in / Sign up (no app destinations).
  if (!isAuthenticated) {
    return (
      <div className="flex items-center gap-1.5">
        <Link href="/login" className={navLinkClass(false)}>
          Log in
        </Link>
        <Button asChild size="sm" className="rounded-full">
          <Link href="/register">Sign up</Link>
        </Button>
      </div>
    );
  }

  return (
    <>
      {/* Desktop nav (authenticated) */}
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

        <span className="mx-1.5 h-5 w-px bg-border" aria-hidden="true" />

        <div className="flex items-center gap-2">
          {playerName && (
            <Link
              href="/portfolio"
              className={cn(
                "flex items-center gap-2 rounded-full border border-border bg-muted/60 py-1 pl-1 pr-3 text-sm text-foreground transition-colors hover:border-border-strong",
                FOCUS_RING,
              )}
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
              className={cn(
                "rounded-full px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
                FOCUS_RING,
              )}
            >
              Log out
            </button>
          </form>
        </div>
      </nav>

      {/* Mobile menu button (authenticated) */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Close menu" : "Open menu"}
        aria-expanded={open}
        className={cn(
          "grid h-11 w-11 place-items-center rounded-full border border-border bg-muted/60 text-foreground transition-colors hover:border-border-strong sm:hidden",
          FOCUS_RING,
        )}
      >
        {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
      </button>

      {/* Mobile sheet — rendered only when open (avoids duplicate labels). */}
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
                    FOCUS_RING,
                    active
                      ? "bg-brand-primary/15 font-semibold text-foreground"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  {label}
                </Link>
              );
            })}
            <div className="my-1 h-px bg-border" />
            <form action={logoutAction}>
              <button
                type="submit"
                className={cn(
                  "w-full rounded-xl px-4 py-3 text-left text-base font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
                  FOCUS_RING,
                )}
              >
                Log out
              </button>
            </form>
          </nav>
        </div>
      )}
    </>
  );
}
