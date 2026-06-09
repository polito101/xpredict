import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import { cookies } from "next/headers";
import "./globals.css";
import { Toaster } from "@/components/ui/sonner";
import { SiteFrame } from "@/components/site-frame";
import { Aurora } from "@/components/brand/aurora";
import {
  fetchBrandingPublic,
  DEFAULT_BRANDING,
} from "@/lib/branding-public";
import { pickReadableForeground } from "@/lib/brand-color";

/**
 * Type pairing (v1.2 Phase 19): Inter for body (legible, neutral) + Space Grotesk
 * for display/headings/big-numbers (geometric, echoes the angular "X"). Exposed
 * as CSS vars `--font-inter` / `--font-space-grotesk` that globals.css consumes
 * (body + h1–h3 + `.font-display`). `display:"swap"` avoids invisible text.
 */
const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-space-grotesk",
});

export const metadata: Metadata = {
  title: "XPrediction — The prediction-market platform",
  description:
    "XPrediction connects the entire prediction-market ecosystem — run native markets, integrate external ones, and launch your own. White-label, API-first infrastructure.",
};

/** Server-only backend base (never leaks into the client bundle). */
function backendUrl(): string {
  return process.env.BACKEND_URL || "http://localhost:8000";
}

/**
 * Best-effort fetch of the signed-in player's display name (the new account
 * affordance — `GET /auth/users/me` carries `display_name`/`email`). Self-scoped
 * by the player's own HttpOnly cookie, forwarded server-side; the cookie value
 * never reaches client JS. Degrades to null on any failure (the nav then shows a
 * generic "Account").
 */
async function fetchPlayerName(session: string): Promise<string | null> {
  try {
    const res = await fetch(`${backendUrl()}/auth/users/me`, {
      headers: { Cookie: `xpredict_session=${session}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    const data = (await res.json()) as {
      display_name?: string | null;
      email?: string | null;
    };
    return data.display_name?.trim() || data.email?.split("@")[0] || null;
  } catch {
    return null;
  }
}

/**
 * Player root layout — runtime theming consumer (ADD-06 / D-10). Restyled to the
 * dark-first "Obsidian & Spark" system in Phase 19; the white-label contract is
 * UNCHANGED: it awaits the PUBLIC `GET /branding/current` on EVERY navigation
 * (`cache:"no-store"`) and injects a `<style>:root{--brand-primary;…}</style>`
 * block from the server-validated hexes, so an operator palette change re-skins
 * the player on its next navigation with NO rebuild/redeploy.
 *
 * Security (T-10-01): the hexes are validated `^#[0-9a-fA-F]{6}$` server-side
 * before persist AND before injection; the layout interpolates ONLY the two
 * validated hex tokens + the derived foreground (one of two constant literals).
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

  // Session presence drives the nav (only the boolean crosses into the tree —
  // never the cookie value). When present, best-effort resolve the display name.
  const session = (await cookies()).get("xpredict_session")?.value;
  const isAuthenticated = Boolean(session);
  const playerName = session ? await fetchPlayerName(session) : null;

  return (
    <html
      lang="en"
      className={`${inter.variable} ${spaceGrotesk.variable} h-full antialiased`}
    >
      <head>
        {/* Validated opaque hex tokens + a foreground derived from primary
            (one of two safe constant literals — never untrusted input). */}
        <style>{`:root{--brand-primary:${b.primary_hex};--brand-primary-foreground:${pickReadableForeground(b.primary_hex)};--brand-secondary:${b.secondary_hex};}`}</style>
      </head>
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <Aurora />
        <SiteFrame
          brandName={b.brand_name}
          logoUrl={b.logo_url}
          isAuthenticated={isAuthenticated}
          playerName={playerName}
        >
          {children}
        </SiteFrame>
        <Toaster />
      </body>
    </html>
  );
}
