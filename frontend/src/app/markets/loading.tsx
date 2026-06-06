/**
 * Route-level loading UI for the app's markets catalog — shown during navigation
 * while the Server Component fetches `/catalog`. Mirrors the markets header +
 * card-grid to avoid layout shift.
 */
import { MarketListSkeleton } from "@/components/market-list-skeleton";
import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <main className="w-full max-w-6xl mx-auto px-4 sm:px-6 py-10">
      <div className="mb-8 flex items-baseline justify-between">
        <Skeleton className="h-9 w-40" aria-hidden="true" />
        <Skeleton className="h-4 w-20" aria-hidden="true" />
      </div>
      <Skeleton className="mb-8 h-11 w-full max-w-xl" aria-hidden="true" />
      <MarketListSkeleton />
    </main>
  );
}
