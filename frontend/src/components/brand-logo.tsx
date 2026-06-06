/**
 * BrandLogo — player-header brand logo / wordmark (ADD-06).
 *
 * Renders the operator's uploaded logo when one is configured; otherwise the
 * DEFAULT XPredict mark (the angular "X" + spark, `XMark`) beside the brand-name
 * wordmark, falling back to "XPredict" when the name is unset. Consumed from the
 * same `/branding/current` payload the root layout already awaits — no extra fetch.
 *
 * Security (T-10-02): an operator logo is rendered ONLY via
 * `<img src="/branding/logo">` (SVG-in-`<img>` does not execute script; the
 * backend serves it with `X-Content-Type-Options: nosniff`). Logo bytes are NEVER
 * inlined into the DOM as markup.
 *
 * Accessibility (A-PALETTE #4): the wordmark text keeps a legible cool-ink layer;
 * brand color is used only as the mark/accent, never as the background of
 * legibility-critical text — a bad operator palette can never make the header
 * name unreadable.
 */
import Link from "next/link";

import { XMark } from "@/components/brand/x-mark";
import { cn } from "@/lib/utils";

/**
 * Resolves the browser-reachable backend base for the logo `<img>`. The
 * `/branding/current` payload returns `logo_url` as a backend-relative path
 * (`/branding/logo`); the Next app and backend are on different origins, so the
 * browser must hit the public `NEXT_PUBLIC_API_URL`. Mirrors `lib/api.ts`.
 */
function publicApiBase(): string {
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

export interface BrandLogoProps {
  brandName: string;
  /** Backend-relative logo path (`/branding/logo`) or null when none is set. */
  logoUrl: string | null;
  className?: string;
}

export function BrandLogo({ brandName, logoUrl, className }: BrandLogoProps) {
  // Visible brand = "XPrediction" (the product). White-label still wins: a real
  // operator name renders verbatim. The legacy default "XPredict" (and an empty
  // name) map to the product brand "XPrediction" so the canonical site is
  // consistent regardless of the backend's stored brand_name.
  const raw = brandName.trim();
  const name = !raw || raw === "XPredict" ? "XPrediction" : raw;

  return (
    <Link
      href="/"
      aria-label={name}
      className={cn(
        "group inline-flex items-center gap-2.5 rounded-lg font-display text-base font-semibold tracking-tight focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        className,
      )}
    >
      {logoUrl ? (
        // eslint-disable-next-line @next/next/no-img-element -- the logo is a
        // dynamic backend asset on a different origin (not a static import), so
        // a raw <img> is correct here; next/image would require remote-pattern
        // config + defeats the per-navigation no-store freshness.
        <img
          src={`${publicApiBase()}${logoUrl}`}
          alt={name}
          className="h-8 w-auto"
        />
      ) : (
        <>
          <XMark className="h-8 w-8 transition-transform duration-300 group-hover:scale-105" />
          <span className="text-foreground">
            {name === "XPrediction" ? (
              <>
                <span className="text-gradient-brand">X</span>
                <span>Prediction</span>
              </>
            ) : (
              name
            )}
          </span>
        </>
      )}
    </Link>
  );
}
