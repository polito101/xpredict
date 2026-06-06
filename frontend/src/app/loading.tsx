/**
 * Route-level loading UI for the public landing (`/`) — a lightweight hero
 * placeholder shown while the Server Component resolves the (best-effort) demo
 * data. The landing body is largely static, so this stays minimal.
 */
import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-20 sm:px-6">
      <div className="flex flex-col gap-5">
        <Skeleton className="h-6 w-72" aria-hidden="true" />
        <Skeleton className="h-14 w-full max-w-2xl" aria-hidden="true" />
        <Skeleton className="h-14 w-3/4 max-w-xl" aria-hidden="true" />
        <Skeleton className="h-5 w-full max-w-lg" aria-hidden="true" />
        <div className="flex gap-3 pt-2">
          <Skeleton className="h-11 w-28" aria-hidden="true" />
          <Skeleton className="h-11 w-44" aria-hidden="true" />
        </div>
      </div>
    </div>
  );
}
