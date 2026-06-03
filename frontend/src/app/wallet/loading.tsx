import { Skeleton } from "@/components/ui/skeleton";

/**
 * Wallet route loading skeleton (v1.1 Fase C) — shown while the Server Component
 * fetches balance + history, so a slow backend never flashes an empty page.
 */
export default function WalletLoading() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-4 py-12 sm:px-6">
      <div className="flex flex-col gap-2">
        <Skeleton className="h-9 w-32" />
        <Skeleton className="h-4 w-64" />
      </div>
      <Skeleton className="h-32 w-full rounded-xl" />
      <div className="flex flex-col gap-3">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    </main>
  );
}
