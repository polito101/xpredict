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
      <CardHeader className="p-6 pb-2">
        <Skeleton className="h-12 w-full" aria-hidden="true" />
      </CardHeader>
      <CardContent className="p-6 pt-0">
        <Skeleton className="h-8 w-full" aria-hidden="true" />
      </CardContent>
      <CardFooter className="p-6 pt-0">
        <Skeleton className="h-4 w-3/4" aria-hidden="true" />
      </CardFooter>
    </Card>
  );
}

export function MarketListSkeleton() {
  return (
    <div
      className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
      aria-busy="true"
    >
      {Array.from({ length: 6 }, (_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}
