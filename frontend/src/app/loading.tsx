/**
 * Route-level loading UI for the homepage catalog browse — shown during
 * navigation while the Server Component fetches `/catalog`. Reuses the shared
 * card-grid skeleton (formerly the homepage Suspense fallback).
 */
import { MarketListSkeleton } from "@/components/market-list-skeleton";

export default function Loading() {
  return (
    <main className="w-full max-w-6xl mx-auto px-4 sm:px-6 py-12">
      <h1 className="mb-8 text-xl font-semibold">Markets</h1>
      <MarketListSkeleton />
    </main>
  );
}
