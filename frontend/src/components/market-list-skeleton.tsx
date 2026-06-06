/**
 * MarketListSkeleton -- loading placeholder grid matching MarketCard dimensions.
 *
 * Renders 6 skeleton cards in the same responsive grid layout as MarketList.
 * Server Component (no "use client").
 */
import { Card, CardHeader, CardContent, CardFooter } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

function SkeletonCard() {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between p-5 pb-3">
        <Skeleton className="h-5 w-20" aria-hidden="true" />
        <Skeleton className="h-5 w-16" aria-hidden="true" />
      </CardHeader>
      <CardContent className="p-5 pt-0">
        <Skeleton className="h-12 w-full" aria-hidden="true" />
      </CardContent>
      <CardFooter className="mt-4 flex-col items-stretch gap-3 p-5 pt-0">
        <Skeleton className="h-8 w-full" aria-hidden="true" />
        <Skeleton className="h-4 w-3/4" aria-hidden="true" />
      </CardFooter>
    </Card>
  );
}

export function MarketListSkeleton() {
  return (
    <div
      className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3"
      aria-busy="true"
    >
      {Array.from({ length: 6 }, (_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}
