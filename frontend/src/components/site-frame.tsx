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

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X } from "lucide-react";

import { BrandLogo } from "@/components/brand-logo";
import { PlayerNav } from "@/components/player-nav";
import { SocialLinks } from "@/components/social-links";

/** In-page section links shown in the landing header (home only), in page order.
 *  Each href targets a real section `id` on `/`:
 *  Pillars(#platform) · WhyXPrediction(#why) · CapabilityGrid(#capabilities) ·
 *  ApiSection(#developers) · DemoShowcase(#demo) · ContactSection(#contact). */
const SECTION_LINKS = [
  { href: "/#platform", label: "Platform" },
  { href: "/#why", label: "Why" },
  { href: "/#capabilities", label: "Capabilities" },
  { href: "/#developers", label: "Developers" },
  { href: "/#demo", label: "Live demo" },
  { href: "/#contact", label: "Contact" },
] as const;

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
  const isLanding = pathname === "/";
  const [sectionsOpen, setSectionsOpen] = useState(false);

  // The admin surface supplies its own chrome — render the page bare. Use a
  // word-boundary check (mirrors the proxy's ADMIN_PROTECTED regex) so a future
  // sibling like /administrators is NOT mistaken for the admin tree.
  if (pathname === "/admin" || pathname.startsWith("/admin/")) {
    return <>{children}</>;
  }

  return (
    <>
      <header className="sticky top-0 z-40 border-b border-border/70 surface-glass">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between gap-3 px-4 sm:px-6">
          <div className="flex items-center gap-2 sm:gap-4 lg:gap-6">
            {/* Hamburger for the in-page section links (mobile/tablet, landing
                only — desktop shows them inline). */}
            {isLanding && (
              <button
                type="button"
                onClick={() => setSectionsOpen((v) => !v)}
                aria-label={sectionsOpen ? "Close sections menu" : "Open sections menu"}
                aria-expanded={sectionsOpen}
                className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-border bg-muted/50 text-foreground transition-colors hover:border-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background lg:hidden"
              >
                {sectionsOpen ? (
                  <X className="h-5 w-5" />
                ) : (
                  <Menu className="h-5 w-5" />
                )}
              </button>
            )}
            <BrandLogo brandName={brandName} logoUrl={logoUrl} />
            {isLanding && (
              <nav className="hidden items-center gap-0.5 lg:flex">
                {SECTION_LINKS.map((l) => (
                  <Link
                    key={l.href}
                    href={l.href}
                    className="rounded-lg px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                  >
                    {l.label}
                  </Link>
                ))}
              </nav>
            )}
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            {/* Social presence — hidden on mobile to keep the compact header
                uncluttered; mobile visitors reach it via the footer. */}
            <SocialLinks className="hidden sm:flex" />
            <span
              className="hidden h-5 w-px bg-border sm:block"
              aria-hidden="true"
            />
            <PlayerNav isAuthenticated={isAuthenticated} playerName={playerName} />
          </div>
        </div>

        {/* Mobile sections sheet (landing only) — the hamburger's section links,
            rendered only when open so the desktop nav stays the single source. */}
        {isLanding && sectionsOpen && (
          <div className="absolute inset-x-0 top-16 z-40 border-b border-border bg-popover/95 shadow-pop backdrop-blur-xl lg:hidden">
            <nav
              className="mx-auto flex w-full max-w-6xl flex-col gap-1 px-4 py-3 sm:px-6"
              aria-label="Section navigation"
            >
              {SECTION_LINKS.map((l) => (
                <Link
                  key={l.href}
                  href={l.href}
                  onClick={() => setSectionsOpen(false)}
                  className="rounded-xl px-4 py-3 text-base font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                >
                  {l.label}
                </Link>
              ))}
            </nav>
          </div>
        )}
      </header>

      <div className="flex-1">{children}</div>

      <footer className="border-t border-border/70 bg-surface/60">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-6 text-xs text-muted-foreground sm:px-6">
          {/* Brand presence: follow XPrediction across socials + the disclaimer. */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
              <div className="flex items-center gap-2">
                <span className="text-subtle-foreground">Follow XPrediction</span>
                <SocialLinks className="-ml-1" />
              </div>
              <Link
                href="mailto:support@xprediction.online"
                className="rounded text-subtle-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              >
                support@xprediction.online
              </Link>
            </div>
            <p className="text-subtle-foreground">
              Play-money tokens have no monetary value.
            </p>
          </div>

          <div className="h-px bg-border/60" aria-hidden="true" />

          {/* Copyright + legal. */}
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
        </div>
      </footer>
    </>
  );
}
