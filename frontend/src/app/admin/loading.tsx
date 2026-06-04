/**
 * Admin dashboard route loading skeleton (v1.1 Fase D — operator polish).
 *
 * Next.js renders this as the Suspense fallback for the `/admin` segment while
 * the Server Component awaits the initial KPI payload (`force-dynamic`, so a
 * slow backend would otherwise flash a blank page on the post-login landing).
 * Mirrors `admin/page.tsx` + the `KpiGrid` layout (header → 5 KPI cards in a
 * grid-cols-1 → sm:2 → lg:3 reflow → volume chart) so there is no layout shift.
 *
 * Server Component (no "use client"). Pattern mirrors `app/portfolio/loading.tsx`.
 */
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

function SkeletonKpiCard() {
  return (
    <Card>
      <CardHeader className="pb-2">
        <Skeleton className="h-4 w-28" aria-hidden="true" />
      </CardHeader>
      <CardContent>
        <Skeleton className="h-8 w-24" aria-hidden="true" />
      </CardContent>
    </Card>
  );
}

export default function AdminDashboardLoading() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-12" aria-busy="true">
      <Skeleton className="h-9 w-44" aria-hidden="true" />
      <Skeleton className="mt-2 h-4 w-56" aria-hidden="true" />

      <div className="mt-8 space-y-8">
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <SkeletonKpiCard key={i} />
          ))}
        </div>

        <Card>
          <CardHeader className="pb-2">
            <Skeleton className="h-5 w-48" aria-hidden="true" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-72 w-full" aria-hidden="true" />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
