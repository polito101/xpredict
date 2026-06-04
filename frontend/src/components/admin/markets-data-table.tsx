/**
 * Plan 12-05 — Markets data table (TanStack Table v8, server-driven).
 *
 * Clone of `users-data-table.tsx` (ADM-01): the whole server-driven state
 * machine (`manualPagination`/`manualSorting`, the firstRender-skip fetch
 * effect, `resetToFirstPage` on every filter change, rows-as-links a11y,
 * skeleton/empty/error states, `PaginationControls`) transfers verbatim — only
 * the endpoint (`fetchMarkets`), the columns, and the filter bar change.
 *
 * Columns: question / source (SourceBadge) / status (MarketStatusBadge) /
 * category / deadline / bet_count / created_at / "View". The whole row is a
 * keyboard-accessible link to `/admin/markets/{id}`.
 *
 * Filter bar (swap of the single status Select): THREE Selects — source
 * (HOUSE/POLYMARKET), status (the 5 MarketStatus), category (free-text). No
 * search/date-range/CSV-export for markets (12-RESEARCH lists none).
 *
 * Default sort: created_at desc. PAGE_SIZE = 20.
 */
"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  type ColumnDef,
  type SortingState,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Skeleton } from "@/components/ui/skeleton";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { MarketStatusBadge } from "@/components/admin/market-status-badge";
import { SourceBadge } from "@/components/source-badge";
import { fetchMarkets } from "@/lib/admin-markets-api";
import type {
  PaginatedResponse,
  MarketListItem,
  MarketListParams,
  MarketSource,
  MarketStatus,
} from "@/lib/admin-markets-types";
import { formatDate, truncate } from "@/lib/admin-format";

const PAGE_SIZE = 20;
const SOURCE_ALL = "all";
const STATUS_ALL = "all";

const STATUS_OPTIONS: MarketStatus[] = [
  "OPEN",
  "CLOSED",
  "RESOLVED",
  "CANCELLED",
  "DRAFT",
];

const columns: ColumnDef<MarketListItem>[] = [
  {
    accessorKey: "question",
    header: "Question",
    enableSorting: true,
    cell: ({ row }) => {
      const q = row.original.question;
      if (q.length <= 48) {
        return (
          <span className="font-medium text-zinc-900 dark:text-zinc-50">
            {q}
          </span>
        );
      }
      return (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="cursor-default font-medium text-zinc-900 dark:text-zinc-50">
              {truncate(q, 48)}
            </span>
          </TooltipTrigger>
          <TooltipContent>{q}</TooltipContent>
        </Tooltip>
      );
    },
  },
  {
    accessorKey: "source",
    header: "Source",
    enableSorting: true,
    cell: ({ row }) => (
      <SourceBadge
        source={row.original.source}
        sourceUrl={row.original.source_url}
      />
    ),
  },
  {
    accessorKey: "status",
    header: "Status",
    enableSorting: true,
    cell: ({ row }) => <MarketStatusBadge status={row.original.status} />,
  },
  {
    accessorKey: "category",
    header: "Category",
    enableSorting: true,
    cell: ({ row }) => {
      const c = row.original.category;
      if (!c) return <span className="text-zinc-400">—</span>;
      return <span className="text-zinc-600 dark:text-zinc-400">{c}</span>;
    },
  },
  {
    accessorKey: "deadline",
    header: "Deadline",
    enableSorting: true,
    cell: ({ row }) => (
      <span className="text-zinc-600 dark:text-zinc-400">
        {formatDate(row.original.deadline)}
      </span>
    ),
  },
  {
    accessorKey: "bet_count",
    header: "Bets",
    enableSorting: true,
    cell: ({ row }) => (
      <span className="tabular-nums">{row.original.bet_count}</span>
    ),
  },
  {
    accessorKey: "created_at",
    header: "Created",
    enableSorting: true,
    cell: ({ row }) => (
      <span className="text-zinc-600 dark:text-zinc-400">
        {formatDate(row.original.created_at)}
      </span>
    ),
  },
  {
    id: "actions",
    header: "",
    enableSorting: false,
    cell: () => (
      <span className="text-sm font-medium text-zinc-900 underline-offset-4 group-hover:underline dark:text-zinc-50">
        View
      </span>
    ),
  },
];

export function MarketsDataTable({
  initialData,
}: {
  initialData: PaginatedResponse<MarketListItem>;
}) {
  const router = useRouter();

  const [data, setData] =
    React.useState<PaginatedResponse<MarketListItem>>(initialData);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(false);

  // Filter / sort / pagination state.
  const [source, setSource] = React.useState<MarketSource | "">("");
  const [status, setStatus] = React.useState<MarketStatus | "">("");
  const [category, setCategory] = React.useState("");
  const [sorting, setSorting] = React.useState<SortingState>([
    { id: "created_at", desc: true },
  ]);
  const [page, setPage] = React.useState(1);

  // Skip the very first fetch — the server component already provided page 1.
  const firstRender = React.useRef(true);

  const currentFilters: MarketListParams = React.useMemo(() => {
    const sort = sorting[0];
    return {
      source: source || undefined,
      status: status || undefined,
      category: category || undefined,
      sort_by: sort?.id ?? "created_at",
      sort_order: sort ? (sort.desc ? "desc" : "asc") : "desc",
    };
  }, [source, status, category, sorting]);

  React.useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(false);
    fetchMarkets({ ...currentFilters, page, page_size: PAGE_SIZE })
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
  }, [currentFilters, page]);

  // Filter changes reset to page 1.
  const resetToFirstPage = React.useCallback(() => setPage(1), []);

  const table = useReactTable({
    data: data.items,
    columns,
    state: { sorting },
    manualPagination: true,
    manualSorting: true,
    rowCount: data.total,
    onSortingChange: (updater) => {
      setSorting(updater);
      resetToFirstPage();
    },
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex flex-col gap-6">
        {/* Filter bar */}
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex flex-col gap-1">
            <span className="text-xs font-medium text-zinc-500">Source</span>
            <Select
              value={source === "" ? SOURCE_ALL : source}
              onValueChange={(v) => {
                setSource(v === SOURCE_ALL ? "" : (v as MarketSource));
                resetToFirstPage();
              }}
            >
              <SelectTrigger className="w-[160px]" aria-label="Filter by source">
                <SelectValue placeholder="All sources" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={SOURCE_ALL}>All sources</SelectItem>
                <SelectItem value="HOUSE">House</SelectItem>
                <SelectItem value="POLYMARKET">Polymarket</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-xs font-medium text-zinc-500">Status</span>
            <Select
              value={status === "" ? STATUS_ALL : status}
              onValueChange={(v) => {
                setStatus(v === STATUS_ALL ? "" : (v as MarketStatus));
                resetToFirstPage();
              }}
            >
              <SelectTrigger className="w-[160px]" aria-label="Filter by status">
                <SelectValue placeholder="All statuses" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={STATUS_ALL}>All statuses</SelectItem>
                {STATUS_OPTIONS.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-xs font-medium text-zinc-500">Category</span>
            <Input
              type="text"
              value={category}
              onChange={(e) => {
                setCategory(e.target.value);
                resetToFirstPage();
              }}
              placeholder="Filter by category..."
              aria-label="Filter by category"
              className="w-[200px]"
            />
          </div>
        </div>

        {/* Table */}
        <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
          <Table>
            <TableHeader className="bg-zinc-50 dark:bg-zinc-900">
              {table.getHeaderGroups().map((hg) => (
                <TableRow key={hg.id}>
                  {hg.headers.map((header) => {
                    const canSort = header.column.getCanSort();
                    const sorted = header.column.getIsSorted();
                    return (
                      <TableHead
                        key={header.id}
                        aria-sort={
                          sorted === "asc"
                            ? "ascending"
                            : sorted === "desc"
                              ? "descending"
                              : "none"
                        }
                        className={
                          canSort ? "cursor-pointer select-none" : undefined
                        }
                        onClick={
                          canSort
                            ? header.column.getToggleSortingHandler()
                            : undefined
                        }
                      >
                        <span className="inline-flex items-center gap-1">
                          {flexRender(
                            header.column.columnDef.header,
                            header.getContext(),
                          )}
                          {sorted === "asc"
                            ? " ↑"
                            : sorted === "desc"
                              ? " ↓"
                              : ""}
                        </span>
                      </TableHead>
                    );
                  })}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody aria-busy={loading}>
              {loading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={`skeleton-${i}`}>
                    {columns.map((_col, ci) => (
                      <TableCell key={ci}>
                        <Skeleton className="h-4 w-full" aria-hidden="true" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : error ? (
                <TableRow>
                  <TableCell
                    colSpan={columns.length}
                    className="py-12 text-center"
                  >
                    <p className="text-sm font-medium text-red-700 dark:text-red-400">
                      Failed to load data
                    </p>
                    <p className="mt-1 text-sm text-zinc-500">
                      Something went wrong while loading this page. Please try
                      again.
                    </p>
                  </TableCell>
                </TableRow>
              ) : data.items.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={columns.length}
                    className="py-12 text-center"
                  >
                    <p className="text-sm font-medium text-zinc-900 dark:text-zinc-50">
                      No markets found
                    </p>
                    <p className="mt-1 text-sm text-zinc-500">
                      No markets match your current filters. Try adjusting the
                      search or filter criteria.
                    </p>
                  </TableCell>
                </TableRow>
              ) : (
                table.getRowModel().rows.map((row) => (
                  <TableRow
                    key={row.id}
                    role="link"
                    tabIndex={0}
                    aria-label={`View market ${row.original.question}`}
                    className="group cursor-pointer"
                    onClick={() =>
                      router.push(`/admin/markets/${row.original.id}`)
                    }
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        router.push(`/admin/markets/${row.original.id}`);
                      }
                    }}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id}>
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext(),
                        )}
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>

        <PaginationControls
          page={data.page}
          pages={data.pages}
          onPageChange={setPage}
          disabled={loading}
        />
      </div>
    </TooltipProvider>
  );
}
