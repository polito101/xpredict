/**
 * Admin user-detail route loading skeleton (v1.1 Fase D — operator polish).
 *
 * Suspense fallback for `/admin/users/[id]` while the Server Component fetches
 * the user detail (`force-dynamic`). Mirrors `users/[id]/page.tsx` (back link →
 * email/name header + ban action → Profile/Wallet/Bets tabs + content) so the
 * moderation view never flashes blank on a slow load.
 *
 * Server Component (no "use client").
 */
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export default function AdminUserDetailLoading() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-12" aria-busy="true">
      <Skeleton className="mb-8 h-4 w-28" aria-hidden="true" />

      <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-2">
          <Skeleton className="h-8 w-64 max-w-full" aria-hidden="true" />
          <Skeleton className="h-4 w-40" aria-hidden="true" />
        </div>
        <Skeleton className="h-10 w-24" aria-hidden="true" />
      </div>

      <div className="flex gap-2">
        <Skeleton className="h-9 w-24" aria-hidden="true" />
        <Skeleton className="h-9 w-24" aria-hidden="true" />
        <Skeleton className="h-9 w-24" aria-hidden="true" />
      </div>

      <Card className="mt-4">
        <CardContent className="flex flex-col gap-4 py-6">
          <Skeleton className="h-4 w-full" aria-hidden="true" />
          <Skeleton className="h-4 w-3/4" aria-hidden="true" />
          <Skeleton className="h-4 w-2/3" aria-hidden="true" />
        </CardContent>
      </Card>
    </div>
  );
}
