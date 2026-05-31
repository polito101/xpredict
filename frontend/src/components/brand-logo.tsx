/**
 * Plan 10-05 — player-header brand logo / wordmark (ADD-06, UI-SPEC Component
 * Inventory + Accessibility guardrail).
 *
 * Renders the operator's logo when one is configured, else the brand name as a
 * wordmark, falling back to "XPredict" when the name is unset. Consumed from the
 * same `/branding/current` payload the root layout already awaits — no extra
 * fetch.
 *
 * Security (T-10-02): the logo is rendered ONLY via `<img src="/branding/logo">`
 * (SVG-in-`<img>` does not execute script; the backend serves it with
 * `X-Content-Type-Options: nosniff`). The logo bytes are NEVER inlined into the
 * DOM as markup.
 *
 * Accessibility (UI-SPEC A-PALETTE guardrail #4): the wordmark text keeps the
 * zinc/foreground ink layer — brand color is used ONLY as a subtle accent dot,
 * never as the background of legibility-critical text. A bad operator palette
 * therefore can never make the header name unreadable.
 */
import Link from "next/link";

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
  // Empty/whitespace brand name → the XPredict wordmark fallback.
  const name = brandName.trim() || "XPredict";

  return (
    <Link
      href="/"
      aria-label={name}
      className={cn(
        "inline-flex items-center gap-2 font-semibold tracking-tight text-zinc-900",
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
          className="h-7 w-auto"
        />
      ) : (
        <>
          {/* Brand-color accent dot — the ONLY place --brand-primary touches the
              header; the wordmark text below stays zinc ink (A-PALETTE #4). */}
          <span
            aria-hidden="true"
            className="h-2.5 w-2.5 rounded-full bg-brand-primary"
          />
          <span className="text-base">{name}</span>
        </>
      )}
    </Link>
  );
}
