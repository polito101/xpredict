/**
 * Plan 09-04 — Portfolio route loading skeleton (ROADMAP SC#5 / UI-SPEC).
 *
 * Next.js renders this `loading.tsx` as the Suspense fallback for the
 * `/portfolio` route segment during the server data load. It mirrors the
 * `portfolio/page.tsx` layout (max-w-2xl header + Open/Settled sections) using
 * the existing Skeleton vocabulary so there is no layout shift. The page keeps
 * its existing empty-degradation for errors; this only covers the loading
 * window.
 *
 * Server Component (no "use client").
 */
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

function SkeletonPositionCard() {
  return (
    <Card>
      <CardHeader className="gap-2">
        <Skeleton className="h-4 w-48" aria-hidden="true" />
        <Skeleton className="h-5 w-56" aria-hidden="true" />
      </CardHeader>
      <CardContent className="flex items-center justify-between">
        <Skeleton className="h-4 w-32" aria-hidden="true" />
        <Skeleton className="h-4 w-24" aria-hidden="true" />
      </CardContent>
    </Card>
  );
}

export default function PortfolioLoading() {
  return (
    <main
      className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-6 py-12"
      aria-busy="true"
    >
      <header className="flex flex-col gap-1">
        <Skeleton className="h-9 w-44" aria-hidden="true" />
        <Skeleton className="h-4 w-72" aria-hidden="true" />
      </header>

      <section className="flex flex-col gap-3">
        <Skeleton className="h-6 w-40" aria-hidden="true" />
        <SkeletonPositionCard />
        <SkeletonPositionCard />
      </section>

      <section className="flex flex-col gap-3">
        <Skeleton className="h-6 w-44" aria-hidden="true" />
        <SkeletonPositionCard />
      </section>
    </main>
  );
}
