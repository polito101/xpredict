/**
 * Plan 09 UI-audit follow-up — route error boundary for `/markets/[slug]`.
 *
 * The page-level `try/catch` in `page.tsx` only covers the SSR fetch; if a
 * client component on this route (`MarketDetailLiveOdds`, `PriceHistorySection`)
 * throws during render, Next.js would otherwise fall through to the root
 * boundary. This dedicated segment `error.tsx` keeps the spec-toned
 * "Unable to load this market" copy (UI-SPEC §Copywriting — fetch-failure) and
 * adds a retry affordance via the Next.js `reset()` primitive, plus a
 * "Back to markets" escape hatch mirroring the not-found state.
 *
 * Visuals match the in-page `MarketErrorState`: centered `py-24`, `text-3xl`
 * page H1 (UI-SPEC Display/Page-H1 role), rose accent, `text-sm` body.
 */
"use client";

import { useEffect } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

const PAGE_SHELL = "w-full max-w-6xl mx-auto px-4 sm:px-6 py-12";

export default function MarketDetailError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Surface the render error to the console for diagnostics; the digest is
    // the server-side correlation id Next.js attaches in production.
    console.error("Market detail route error:", error);
  }, [error]);

  return (
    <main className={PAGE_SHELL}>
      <div
        className="flex flex-col items-center justify-center py-24 text-center"
        role="alert"
      >
        <h1 className="font-display text-3xl font-semibold tracking-tight text-red-400">
          Unable to load this market
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Something went wrong. Try refreshing the page.
        </p>
        <div className="mt-6 flex items-center gap-3">
          <Button type="button" size="lg" onClick={() => reset()}>
            Try again
          </Button>
          <Link
            href="/"
            className="text-sm text-foreground underline underline-offset-4 hover:text-brand-primary"
          >
            Back to markets
          </Link>
        </div>
      </div>
    </main>
  );
}
