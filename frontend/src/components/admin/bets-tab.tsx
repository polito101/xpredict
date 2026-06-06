/**
 * Plan 08-03 — Bets tab (user detail).
 *
 * Paginated bets table fetched client-side via `fetchUserBets`. Columns per
 * UI-SPEC: Market (truncated 40 + tooltip), Outcome, Stake, Status badge
 * (Won = emerald, Lost = red, Open = zinc secondary), P&L (positive emerald,
 * negative red, open shows "--"). `PaginationControls` at the bottom.
 *
 * MONEY DISCIPLINE: stake + pnl are rendered through `formatMoney` (string ops).
 * The P&L sign/colour is decided by inspecting the string's leading "-" — never
 * by parsing to a number. Loading / empty / error states per UI-SPEC.
 */
"use client";

import * as React from "react";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { fetchUserBets } from "@/lib/admin-api";
import type { PaginatedResponse, UserBetItem } from "@/lib/admin-types";
import { formatMoney, truncate } from "@/lib/admin-format";

const PAGE_SIZE = 20;
const COL_COUNT = 5;

/** Map a free-form bet status string to a Badge variant + label. */
function statusBadge(status: string) {
  const s = status.toLowerCase();
  if (s === "won") {
    return (
      <Badge className="bg-emerald-500/15 text-emerald-400">
        Won
      </Badge>
    );
  }
  if (s === "lost") {
    return (
      <Badge className="bg-red-500/15 text-red-400">
        Lost
      </Badge>
    );
  }
  if (s === "open") {
    return <Badge variant="secondary">Open</Badge>;
  }
  // Unknown / future status: show it verbatim in a neutral chip.
  return (
    <Badge variant="secondary" className="capitalize">
      {status}
    </Badge>
  );
}

/** Render P&L from the money string — sign/colour off the leading "-". */
function PnlCell({ pnl }: { pnl: string | null }) {
  if (pnl == null) {
    return <span className="text-subtle-foreground">—</span>;
  }
  const negative = pnl.trim().startsWith("-");
  return (
    <span
      className={
        "tabular-nums font-medium " +
        (negative
          ? "text-red-400"
          : "text-emerald-400")
      }
    >
      {formatMoney(pnl)}
    </span>
  );
}

export function BetsTab({ userId }: { userId: string }) {
  const [data, setData] =
    React.useState<PaginatedResponse<UserBetItem> | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(false);
  const [page, setPage] = React.useState(1);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);
    fetchUserBets(userId, page, PAGE_SIZE)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [userId, page]);

  const items = data?.items ?? [];

  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex flex-col gap-3">
        <div className="overflow-x-auto rounded-lg border border-border">
          <Table>
            <TableHeader className="bg-surface">
              <TableRow>
                <TableHead>Market</TableHead>
                <TableHead>Outcome</TableHead>
                <TableHead>Stake</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>P&amp;L</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody aria-busy={loading}>
              {loading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={`skeleton-${i}`}>
                    {Array.from({ length: COL_COUNT }).map((_c, ci) => (
                      <TableCell key={ci}>
                        <Skeleton className="h-4 w-full" aria-hidden="true" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : error ? (
                <TableRow>
                  <TableCell colSpan={COL_COUNT} className="py-12 text-center">
                    <p className="text-sm font-medium text-red-400">
                      Failed to load data
                    </p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Something went wrong while loading this page. Please try
                      again.
                    </p>
                  </TableCell>
                </TableRow>
              ) : items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={COL_COUNT} className="py-12 text-center">
                    <p className="text-sm font-medium text-foreground">
                      No bets placed
                    </p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      This user has not placed any bets yet.
                    </p>
                  </TableCell>
                </TableRow>
              ) : (
                items.map((bet) => (
                  <TableRow key={bet.id}>
                    <TableCell className="max-w-xs">
                      {bet.market_question.length <= 40 ? (
                        <span>{bet.market_question}</span>
                      ) : (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="cursor-default">
                              {truncate(bet.market_question, 40)}
                            </span>
                          </TooltipTrigger>
                          <TooltipContent className="max-w-sm">
                            {bet.market_question}
                          </TooltipContent>
                        </Tooltip>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {bet.outcome_label}
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {formatMoney(bet.stake)}
                    </TableCell>
                    <TableCell>{statusBadge(bet.status)}</TableCell>
                    <TableCell>
                      <PnlCell pnl={bet.pnl} />
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
        {data && (
          <PaginationControls
            page={data.page}
            pages={data.pages}
            onPageChange={setPage}
            disabled={loading}
          />
        )}
      </div>
    </TooltipProvider>
  );
}
