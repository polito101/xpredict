/**
 * RetryError — a non-silent failure state (v1.1 Fase C).
 *
 * Replaces degrading a failed server fetch to a misleading "0" / empty list:
 * tells the player something went wrong and offers a retry. `router.refresh()`
 * re-runs the Server Component (and its fetch) without a full reload.
 */
"use client";

import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";

export function RetryError({
  title,
  message,
}: {
  title: string;
  message?: string;
}) {
  const router = useRouter();
  return (
    <div
      role="alert"
      className="flex flex-col items-start gap-3 rounded-2xl border border-border bg-surface p-6"
    >
      <div className="flex flex-col gap-1">
        <p className="text-sm font-semibold text-foreground">
          {title}
        </p>
        <p className="text-sm text-muted-foreground">
          {message ?? "Something went wrong loading this. Please try again."}
        </p>
      </div>
      <Button type="button" variant="outline" onClick={() => router.refresh()}>
        Try again
      </Button>
    </div>
  );
}
