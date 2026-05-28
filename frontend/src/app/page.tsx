/**
 * Home page -- displays the market catalog.
 *
 * Replaces the Phase 1 scaffold placeholder with a real market list.
 * Uses React Suspense with MarketListSkeleton as the loading fallback.
 */
import { Suspense } from "react";
import MarketList from "@/components/market-list";
import { MarketListSkeleton } from "@/components/market-list-skeleton";

export default function Home() {
  return (
    <main className="w-full max-w-6xl mx-auto px-4 sm:px-6 py-12">
      <h1 className="text-xl font-semibold mb-8">Markets</h1>
      <Suspense fallback={<MarketListSkeleton />}>
        <MarketList />
      </Suspense>
    </main>
  );
}
