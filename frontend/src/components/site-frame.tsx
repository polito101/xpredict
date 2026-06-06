/**
 * SiteFrame — the player/landing chrome (header + footer), Phase 19.
 *
 * Rendered by the root layout around every route. It hides itself on `/admin/*`
 * so the backoffice (which has its OWN header/footer in `app/admin/layout.tsx`)
 * is not double-framed by the player chrome. The branding + session props are
 * resolved server-side in the root layout and passed in; this client component
 * only branches on the pathname.
 */
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { BrandLogo } from "@/components/brand-logo";
import { PlayerNav } from "@/components/player-nav";

export function SiteFrame({
  brandName,
  logoUrl,
  isAuthenticated,
  playerName,
  children,
}: {
  brandName: string;
  logoUrl: string | null;
  isAuthenticated: boolean;
  playerName: string | null;
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  // The admin surface supplies its own chrome — render the page bare. Use a
  // word-boundary check (mirrors the proxy's ADMIN_PROTECTED regex) so a future
  // sibling like /administrators is NOT mistaken for the admin tree.
  if (pathname === "/admin" || pathname.startsWith("/admin/")) {
    return <>{children}</>;
  }

  return (
    <>
      <header className="sticky top-0 z-40 border-b border-border/70 surface-glass">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
          <BrandLogo brandName={brandName} logoUrl={logoUrl} />
          <PlayerNav isAuthenticated={isAuthenticated} playerName={playerName} />
        </div>
      </header>

      <div className="flex-1">{children}</div>

      <footer className="border-t border-border/70 bg-surface/60">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-2 px-4 py-6 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div className="flex items-center gap-2">
            <span className="text-subtle-foreground">© XPrediction</span>
            <span aria-hidden="true" className="text-border-strong">
              ·
            </span>
            <nav className="flex flex-wrap gap-x-4 gap-y-1">
              <Link
                href="https://github.com/polito101/xpredict/blob/main/docs/terms-of-service.md"
                className="rounded transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              >
                Terms of Service
              </Link>
              <Link
                href="https://github.com/polito101/xpredict/blob/main/docs/regulatory.md"
                className="rounded transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              >
                Token policy
              </Link>
            </nav>
          </div>
          <p className="text-subtle-foreground">
            Play-money tokens have no monetary value.
          </p>
        </div>
      </footer>
    </>
  );
}
