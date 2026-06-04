/**
 * Admin branding route loading skeleton (v1.1 Fase D — operator polish).
 *
 * Suspense fallback for `/admin/branding` while the Server Component pre-fetches
 * the persisted tenant config (`force-dynamic`). Mirrors `branding/page.tsx`
 * (header → form card with brand name + 2 colors + logo + save) so the branding
 * editor never flashes an empty form on a slow load.
 *
 * Server Component (no "use client").
 */
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

function SkeletonField() {
  return (
    <div className="flex flex-col gap-2">
      <Skeleton className="h-4 w-28" aria-hidden="true" />
      <Skeleton className="h-10 w-full max-w-sm" aria-hidden="true" />
    </div>
  );
}

export default function AdminBrandingLoading() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-12" aria-busy="true">
      <Skeleton className="h-9 w-40" aria-hidden="true" />
      <Skeleton className="mt-2 h-4 w-80 max-w-full" aria-hidden="true" />

      <div className="mt-8">
        <Card>
          <CardContent className="flex flex-col gap-6 py-6">
            <SkeletonField />
            <SkeletonField />
            <SkeletonField />
            <SkeletonField />
            <Skeleton className="h-10 w-32" aria-hidden="true" />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
