/**
 * Plan 08-03 — Wallet tab (user detail).
 *
 * Shows the balance (`text-2xl font-semibold`, $ prefix, 4 decimals via
 * `formatMoney` — string ops, no float parsing), the RechargeForm (disabled
 * when the user is banned), and a paginated transaction history table.
 *
 * Transactions are fetched client-side via `fetchUserTransactions` (server
 * action) with `PaginationControls`. The `kind` field drives the sign + colour:
 * credits in emerald with a `+` prefix, debits in red with a `-` prefix
 * (`formatSignedAmount`). Columns: Type, Amount, Reason, Date.
 *
 * After a successful recharge, `onRecharged()` refetches the parent user (so the
 * balance updates) and we bump a local reload key to re-pull page 1 of the
 * transactions. Loading / empty / error states per UI-SPEC.
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
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { RechargeForm } from "@/components/admin/recharge-form";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { fetchUserTransactions } from "@/lib/admin-api";
import type {
  PaginatedResponse,
  UserDetail,
  UserTransactionItem,
} from "@/lib/admin-types";
import {
  formatMoney,
  formatSignedAmount,
  formatTimestamp,
} from "@/lib/admin-format";

const PAGE_SIZE = 20;
const COL_COUNT = 4;

export function WalletTab({
  user,
  onRecharged,
}: {
  user: UserDetail;
  onRecharged: () => void;
}) {
  const userId = user.id;
  const banned = user.status === "banned";

  const [data, setData] =
    React.useState<PaginatedResponse<UserTransactionItem> | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(false);
  const [page, setPage] = React.useState(1);
  // Bumped after a recharge to force a page-1 refetch of the transaction list.
  const [reloadKey, setReloadKey] = React.useState(0);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);
    fetchUserTransactions(userId, page, PAGE_SIZE)
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
  }, [userId, page, reloadKey]);

  const handleRecharged = React.useCallback(() => {
    onRecharged(); // refetch parent user -> balance updates
    setPage(1);
    setReloadKey((k) => k + 1); // re-pull transactions page 1
  }, [onRecharged]);

  const items = data?.items ?? [];

  return (
    <div className="flex flex-col gap-6">
      {/* Balance — de-emphasise a zero balance per UI-SPEC. "Zero" is detected
          with string ops only (no float parsing): no 1-9 digit present. */}
      <div className="flex flex-col gap-1">
        <span className="text-sm font-medium text-zinc-500">Balance</span>
        <span
          className={
            "text-2xl font-semibold tabular-nums " +
            (/[1-9]/.test(user.balance)
              ? "text-zinc-900 dark:text-zinc-50"
              : "text-zinc-400 dark:text-zinc-500")
          }
        >
          {formatMoney(user.balance)}
        </span>
      </div>

      <Separator />

      {/* Recharge */}
      <div className="flex flex-col gap-3">
        <span className="text-base font-semibold tracking-tight">Recharge</span>
        <RechargeForm
          userId={userId}
          banned={banned}
          onRecharged={handleRecharged}
        />
      </div>

      <Separator />

      {/* Transaction history */}
      <div className="flex flex-col gap-3">
        <span className="text-base font-semibold tracking-tight">
          Transaction History
        </span>
        <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
          <Table>
            <TableHeader className="bg-zinc-50 dark:bg-zinc-900">
              <TableRow>
                <TableHead>Type</TableHead>
                <TableHead>Amount</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>Date</TableHead>
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
                    <p className="text-sm font-medium text-red-700 dark:text-red-400">
                      Failed to load data
                    </p>
                    <p className="mt-1 text-sm text-zinc-500">
                      Something went wrong while loading this page. Please try
                      again.
                    </p>
                  </TableCell>
                </TableRow>
              ) : items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={COL_COUNT} className="py-12 text-center">
                    <p className="text-sm font-medium text-zinc-900 dark:text-zinc-50">
                      No transactions
                    </p>
                    <p className="mt-1 text-sm text-zinc-500">
                      This user has no transaction history yet.
                    </p>
                  </TableCell>
                </TableRow>
              ) : (
                items.map((tx) => {
                  const isCredit = tx.kind.toLowerCase() === "credit";
                  return (
                    <TableRow key={tx.id}>
                      <TableCell className="capitalize text-zinc-600 dark:text-zinc-400">
                        {tx.kind}
                      </TableCell>
                      <TableCell
                        className={
                          "tabular-nums font-medium " +
                          (isCredit
                            ? "text-emerald-700 dark:text-emerald-400"
                            : "text-red-700 dark:text-red-400")
                        }
                      >
                        {formatSignedAmount(
                          tx.amount,
                          isCredit ? "credit" : "debit",
                        )}
                      </TableCell>
                      <TableCell className="text-zinc-600 dark:text-zinc-400">
                        {tx.reason ?? <span className="text-zinc-400">—</span>}
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-zinc-600 dark:text-zinc-400">
                        {formatTimestamp(tx.created_at)}
                      </TableCell>
                    </TableRow>
                  );
                })
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
    </div>
  );
}
