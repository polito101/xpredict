/**
 * Plan 09-04 — Market-detail loading skeleton (MKT-03 / ROADMAP SC#5).
 *
 * Mirrors `market-list-skeleton.tsx` (Card + Skeleton blocks, aria-busy /
 * aria-hidden) and the two-column detail shell so there is NO layout shift
 * when the real content resolves: title, an always-visible "Resolution
 * criteria" block, an `h-64` chart-area block (the SAME box as the real chart
 * wrapper), the activity feed, and the sticky order panel.
 *
 * Server Component (no "use client").
 */
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function MarketDetailSkeleton() {
  return (
    <div aria-busy="true">
      {/* Header: question + source/live cluster */}
      <div className="mb-8 flex flex-col gap-3">
        <Skeleton className="h-9 w-3/4" aria-hidden="true" />
        <Skeleton className="h-4 w-32" aria-hidden="true" />
      </div>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
        {/* Left column: criteria + chart + activity */}
        <div className="flex flex-col gap-8 lg:col-span-2">
          {/* Description */}
          <div className="flex flex-col gap-2">
            <Skeleton className="h-4 w-full" aria-hidden="true" />
            <Skeleton className="h-4 w-5/6" aria-hidden="true" />
          </div>

          {/* Resolution criteria card */}
          <Card>
            <CardHeader>
              <Skeleton className="h-5 w-40" aria-hidden="true" />
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              <Skeleton className="h-4 w-full" aria-hidden="true" />
              <Skeleton className="h-4 w-2/3" aria-hidden="true" />
            </CardContent>
          </Card>

          {/* Chart area — same h-64 box as the real chart (no layout shift) */}
          <div className="flex flex-col gap-2">
            <Skeleton className="h-5 w-32" aria-hidden="true" />
            <Skeleton className="h-64 w-full" aria-hidden="true" />
          </div>

          {/* Activity */}
          <div className="flex flex-col gap-2">
            <Skeleton className="h-5 w-36" aria-hidden="true" />
            <Skeleton className="h-4 w-full" aria-hidden="true" />
            <Skeleton className="h-4 w-5/6" aria-hidden="true" />
          </div>
        </div>

        {/* Right column: sticky order panel */}
        <div className="lg:col-span-1">
          <Card className="lg:sticky lg:top-8">
            <CardHeader>
              <Skeleton className="h-5 w-28" aria-hidden="true" />
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <Skeleton className="h-11 w-full" aria-hidden="true" />
              <Skeleton className="h-11 w-full" aria-hidden="true" />
              <Skeleton className="h-11 w-full" aria-hidden="true" />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
