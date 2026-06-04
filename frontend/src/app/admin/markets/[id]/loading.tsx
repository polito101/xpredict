/**
 * Admin market-detail route loading skeleton (v1.1 Fase D — operator polish).
 *
 * Suspense fallback for `/admin/markets/[id]` while the Server Component fetches
 * the market (`force-dynamic`). Mirrors `markets/[id]/page.tsx` (back link →
 * question header + badges → edit form / action buttons) so the market editor
 * never flashes blank on a slow load.
 *
 * Server Component (no "use client").
 */
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export default function AdminMarketDetailLoading() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-12" aria-busy="true">
      <Skeleton className="mb-8 h-4 w-32" aria-hidden="true" />

      <div className="mb-8 flex flex-wrap items-center gap-3">
        <Skeleton className="h-9 w-96 max-w-full" aria-hidden="true" />
        <Skeleton className="h-6 w-20" aria-hidden="true" />
        <Skeleton className="h-6 w-20" aria-hidden="true" />
      </div>

      <Card>
        <CardContent className="flex flex-col gap-6 py-6">
          <div className="flex flex-col gap-2">
            <Skeleton className="h-4 w-28" aria-hidden="true" />
            <Skeleton className="h-10 w-full" aria-hidden="true" />
          </div>
          <div className="flex flex-col gap-2">
            <Skeleton className="h-4 w-28" aria-hidden="true" />
            <Skeleton className="h-24 w-full" aria-hidden="true" />
          </div>
          <div className="flex flex-wrap gap-3">
            <Skeleton className="h-10 w-32" aria-hidden="true" />
            <Skeleton className="h-10 w-32" aria-hidden="true" />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
