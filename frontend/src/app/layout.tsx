import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import { Toaster } from "@/components/ui/sonner";
import { BrandLogo } from "@/components/brand-logo";
import {
  fetchBrandingPublic,
  DEFAULT_BRANDING,
} from "@/lib/branding-public";
import { pickReadableForeground } from "@/lib/brand-color";

/**
 * Premium body typeface (v1.1 Fase A) — replaces the OS system-font stack with
 * Inter, exposed as the `--font-sans` CSS variable that globals.css consumes.
 * `display: "swap"` avoids invisible text while the font loads.
 */
const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: "XPredict",
  description: "White-label prediction market platform.",
};

/**
 * Player root layout — runtime theming consumer (ADD-06 / D-10, Plan 10-05).
 *
 * Async Server Component: awaits the PUBLIC `GET /branding/current` on EVERY
 * navigation (the helper uses `cache: "no-store"`), then injects a
 * `<style>:root{--brand-primary;--brand-secondary}</style>` block from the
 * server-validated hexes. So an operator palette change in /admin/branding
 * re-skins the player on its next page navigation with NO rebuild/redeploy
 * (SC#5/SC#6) — there is no static color inlining.
 *
 * Safe fallback: if the fetch fails, `DEFAULT_BRANDING` (+ the matching `:root`
 * defaults in globals.css) apply, so the player UI is never unbranded-broken
 * (UI-SPEC accessibility guardrail #3 / T-10-17).
 *
 * Security (T-10-01): the hexes are validated `^#[0-9a-fA-F]{6}$` server-side
 * BEFORE persist AND before injection (Plan 10-01). A valid 6-digit hex cannot
 * contain `<`, `>`, `}`, or quotes, so no `</style>` break-out is possible. The
 * layout interpolates ONLY `b.primary_hex` / `b.secondary_hex` (validated
 * opaque tokens) into the <style> block and NEVER concatenates any other
 * untrusted string there.
 */
export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  let b = DEFAULT_BRANDING;
  try {
    b = await fetchBrandingPublic();
  } catch {
    // /branding/current unreachable → keep DEFAULT_BRANDING (safe fallback).
  }

  return (
    <html lang="en" className={`${inter.variable} h-full antialiased`}>
      <head>
        {/* Validated opaque hex tokens + a foreground derived from primary
            (one of two safe constant literals — never untrusted input). */}
        <style>{`:root{--brand-primary:${b.primary_hex};--brand-primary-foreground:${pickReadableForeground(b.primary_hex)};--brand-secondary:${b.secondary_hex};}`}</style>
      </head>
      <body className="min-h-full flex flex-col">
        <header className="border-b border-zinc-200 bg-white">
          <div className="mx-auto flex h-14 w-full max-w-6xl items-center px-4 sm:px-6">
            <BrandLogo brandName={b.brand_name} logoUrl={b.logo_url} />
          </div>
        </header>
        {children}
        <footer className="border-t border-zinc-200 bg-white">
          <div className="mx-auto flex w-full max-w-6xl flex-col gap-1 px-4 py-4 text-xs text-zinc-500 sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <nav className="flex flex-wrap gap-x-4 gap-y-1">
              <Link
                href="https://github.com/polito101/xpredict/blob/main/docs/terms-of-service.md"
                className="hover:text-zinc-700"
              >
                Terms of Service
              </Link>
              <Link
                href="https://github.com/polito101/xpredict/blob/main/docs/regulatory.md"
                className="hover:text-zinc-700"
              >
                Token policy
              </Link>
            </nav>
            <p>Play-money tokens have no monetary value.</p>
          </div>
        </footer>
        <Toaster />
      </body>
    </html>
  );
}
