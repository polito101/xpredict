/**
 * Plan 08-03 — Reusable pagination controls.
 *
 * "< Prev" / "Next >" buttons + "Page X of Y" text per UI-SPEC. Prev disabled
 * on page 1, Next disabled on the last page. `aria-label` + `aria-disabled`
 * per UI-SPEC §Accessibility. Shared by the user list, transactions, bets, and
 * audit-log tables.
 */
"use client";

import { Button } from "@/components/ui/button";

export function PaginationControls({
  page,
  pages,
  onPageChange,
  disabled = false,
}: {
  page: number;
  pages: number;
  onPageChange: (page: number) => void;
  disabled?: boolean;
}) {
  const totalPages = Math.max(1, pages);
  const isFirst = page <= 1;
  const isLast = page >= totalPages;

  return (
    <div className="flex items-center justify-between pt-4">
      <Button
        type="button"
        variant="outline"
        size="sm"
        aria-label="Previous page"
        aria-disabled={isFirst || disabled}
        disabled={isFirst || disabled}
        onClick={() => onPageChange(page - 1)}
      >
        &lt; Prev
      </Button>
      <span className="text-sm text-muted-foreground" aria-live="polite">
        Page {page} of {totalPages}
      </span>
      <Button
        type="button"
        variant="outline"
        size="sm"
        aria-label="Next page"
        aria-disabled={isLast || disabled}
        disabled={isLast || disabled}
        onClick={() => onPageChange(page + 1)}
      >
        Next &gt;
      </Button>
    </div>
  );
}
