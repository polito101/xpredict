/**
 * Route error boundary for `/events/[slug]`.
 *
 * The page `try/catch` only covers the SSR fetch; if a client component on this
 * route (`MarketDetailLiveOdds`, `PriceHistorySection`, `OrderEntryForm`) throws
 * during render, this dedicated segment boundary keeps the spec-toned "Unable to
 * load this event" copy + a retry (`reset()`) + a "Back to markets" escape hatch.
 */
"use client";

import { useEffect } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

const PAGE_SHELL = "w-full max-w-6xl mx-auto px-4 sm:px-6 py-12";

export default function EventDetailError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Event detail route error:", error);
  }, [error]);

  return (
    <main className={PAGE_SHELL}>
      <div
        className="flex flex-col items-center justify-center py-24 text-center"
        role="alert"
      >
        <h1 className="text-3xl font-semibold tracking-tight text-rose-700">
          Unable to load this event
        </h1>
        <p className="mt-2 text-sm text-zinc-500">
          Something went wrong. Try refreshing the page.
        </p>
        <div className="mt-6 flex items-center gap-3">
          <Button type="button" size="lg" onClick={() => reset()}>
            Try again
          </Button>
          <Link
            href="/"
            className="text-sm text-zinc-900 underline dark:text-zinc-100"
          >
            Back to markets
          </Link>
        </div>
      </div>
    </main>
  );
}
