/**
 * Plan 08-03 — Users data table (TanStack Table v8, server-driven).
 *
 * Columns per D-06: email, display name (truncated + tooltip), status badge,
 * signup date, last activity (relative), balance (money string). The whole row
 * is a clickable link to `/admin/users/{id}` (UI-SPEC §Interaction Contract).
 *
 * Server-side everything: `manualPagination` + `manualSorting` are true; the
 * table holds filter / sort / pagination STATE and refetches via the
 * `fetchUsers` Server Action on every change. Search + filter changes reset to
 * page 1. Loading skeleton (5 rows), empty state, and error state per UI-SPEC.
 *
 * MONEY DISCIPLINE: balance is rendered through `formatMoney` (string ops, no
 * float parsing).
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
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Skeleton } from "@/components/ui/skeleton";
import { AdminSearchInput } from "@/components/admin/admin-search-input";
import {
  DateRangeFilter,
  type DateRange,
} from "@/components/admin/date-range-filter";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { ExportCsvButton } from "@/components/admin/export-csv-button";
import { UserStatusBadge } from "@/components/admin/user-status-badge";
import { fetchUsers } from "@/lib/admin-api";
import type {
  PaginatedResponse,
  UserListItem,
  UserListParams,
  UserStatus,
} from "@/lib/admin-types";
import { formatDate, formatMoney, formatRelativeTime, truncate } from "@/lib/admin-format";

const PAGE_SIZE = 20;
const STATUS_ALL = "all";

const columns: ColumnDef<UserListItem>[] = [
  {
    accessorKey: "email",
    header: "Email",
    enableSorting: true,
    cell: ({ row }) => (
      <span className="font-medium text-zinc-900 dark:text-zinc-50">
        {row.original.email}
      </span>
    ),
  },
  {
    accessorKey: "display_name",
    header: "Name",
    enableSorting: true,
    cell: ({ row }) => {
      const name = row.original.display_name;
      if (!name) return <span className="text-zinc-400">—</span>;
      if (name.length <= 24) return <span>{name}</span>;
      return (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="cursor-default">{truncate(name, 24)}</span>
          </TooltipTrigger>
          <TooltipContent>{name}</TooltipContent>
        </Tooltip>
      );
    },
  },
  {
    accessorKey: "status",
    header: "Status",
    enableSorting: true,
    cell: ({ row }) => <UserStatusBadge status={row.original.status} />,
  },
  {
    accessorKey: "created_at",
    header: "Signup",
    enableSorting: true,
    cell: ({ row }) => (
      <span className="text-zinc-600 dark:text-zinc-400">
        {formatDate(row.original.created_at)}
      </span>
    ),
  },
  {
    accessorKey: "last_activity",
    header: "Activity",
    enableSorting: true,
    cell: ({ row }) => (
      <span className="text-zinc-600 dark:text-zinc-400">
        {formatRelativeTime(row.original.last_activity)}
      </span>
    ),
  },
  {
    accessorKey: "balance",
    header: "Balance",
    enableSorting: true,
    cell: ({ row }) => (
      <span className="tabular-nums">{formatMoney(row.original.balance)}</span>
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

export function UsersDataTable({
  initialData,
}: {
  initialData: PaginatedResponse<UserListItem>;
}) {
  const router = useRouter();

  const [data, setData] = React.useState<PaginatedResponse<UserListItem>>(
    initialData,
  );
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(false);

  // Filter / sort / pagination state.
  const [search, setSearch] = React.useState("");
  const [status, setStatus] = React.useState<UserStatus | "">("");
  const [dateRange, setDateRange] = React.useState<DateRange>({
    from: "",
    to: "",
  });
  const [sorting, setSorting] = React.useState<SortingState>([
    { id: "created_at", desc: true },
  ]);
  const [page, setPage] = React.useState(1);

  // Skip the very first fetch — the server component already provided page 1.
  const firstRender = React.useRef(true);

  const currentFilters: UserListParams = React.useMemo(() => {
    const sort = sorting[0];
    return {
      search: search || undefined,
      status: status || undefined,
      signup_after: dateRange.from ? `${dateRange.from}T00:00:00Z` : undefined,
      signup_before: dateRange.to ? `${dateRange.to}T23:59:59Z` : undefined,
      sort_by: sort?.id ?? "created_at",
      sort_order: sort ? (sort.desc ? "desc" : "asc") : "desc",
    };
  }, [search, status, dateRange, sorting]);

  React.useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(false);
    fetchUsers({ ...currentFilters, page, page_size: PAGE_SIZE })
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

  // Search / filter changes reset to page 1.
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
          <AdminSearchInput
            value={search}
            onChange={(v) => {
              setSearch(v);
              resetToFirstPage();
            }}
            placeholder="Search by email or name..."
            ariaLabel="Search users by email or display name"
          />
          <div className="flex flex-col gap-1">
            <span className="text-xs font-medium text-zinc-500">Status</span>
            <Select
              value={status === "" ? STATUS_ALL : status}
              onValueChange={(v) => {
                setStatus(v === STATUS_ALL ? "" : (v as UserStatus));
                resetToFirstPage();
              }}
            >
              <SelectTrigger className="w-[160px]" aria-label="Filter by status">
                <SelectValue placeholder="All statuses" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={STATUS_ALL}>All statuses</SelectItem>
                <SelectItem value="active">Active</SelectItem>
                <SelectItem value="banned">Banned</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <DateRangeFilter
            value={dateRange}
            onChange={(v) => {
              setDateRange(v);
              resetToFirstPage();
            }}
          />
          <div className="ml-auto">
            <ExportCsvButton filters={currentFilters} />
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
                        className={canSort ? "cursor-pointer select-none" : undefined}
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
                          {sorted === "asc" ? " ↑" : sorted === "desc" ? " ↓" : ""}
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
                  <TableCell colSpan={columns.length} className="py-12 text-center">
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
                  <TableCell colSpan={columns.length} className="py-12 text-center">
                    <p className="text-sm font-medium text-zinc-900 dark:text-zinc-50">
                      No users found
                    </p>
                    <p className="mt-1 text-sm text-zinc-500">
                      No users match your current filters. Try adjusting the
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
                    aria-label={`View user ${row.original.email}`}
                    className="group cursor-pointer"
                    onClick={() =>
                      router.push(`/admin/users/${row.original.id}`)
                    }
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        router.push(`/admin/users/${row.original.id}`);
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
