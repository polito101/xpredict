import { Skeleton } from "@/components/ui/skeleton";

/**
 * LB-B-02 — `/live` route loading skeleton (clones `wallet/loading.tsx`'s shape).
 * Shown while the Server Component mints the session + reads the balance, so a
 * slow backend never flashes an empty page.
 */
export default function LiveLoading() {
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-12 sm:px-6">
      <div className="mb-8 flex flex-col gap-2">
        <Skeleton className="h-9 w-32" />
        <Skeleton className="h-4 w-64" />
      </div>
      <Skeleton className="mb-6 h-20 w-full rounded-xl" />
      <Skeleton className="h-96 w-full rounded-xl" />
    </main>
  );
}
