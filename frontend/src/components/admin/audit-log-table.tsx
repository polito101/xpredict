/**
 * Plan 08-03 — Audit log table (TanStack Table v8, server-driven, read-only).
 *
 * Columns per UI-SPEC: Timestamp (MMM DD HH:mm:ss), Event Type (secondary
 * Badge, font-mono text-xs), Actor (truncated 20 + tooltip), Payload
 * (AuditPayloadViewer — collapsible JSONB, D-12). NO mutation controls anywhere
 * — the audit surface is read-only at the UI level (D-11).
 *
 * Server-side everything: `manualPagination` true, default page_size = 50
 * (D-11). Filter changes (event type Select, actor search, date range) reset to
 * page 1 and refetch via the `fetchAuditLog` Server Action. The `firstRender`
 * ref skips the initial fetch — the server component already provided page 1.
 * Loading skeleton (5 rows), empty state, error state per UI-SPEC.
 */
"use client";

import * as React from "react";
import {
  type ColumnDef,
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
import { Badge } from "@/components/ui/badge";
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
import { AuditPayloadViewer } from "@/components/admin/audit-payload-viewer";
import { fetchAuditLog } from "@/lib/admin-api";
import type {
  AuditLogItem,
  AuditLogParams,
  PaginatedResponse,
} from "@/lib/admin-types";
import { formatTimestamp, truncate } from "@/lib/admin-format";

const PAGE_SIZE = 50;
const EVENT_ALL = "all";

const columns: ColumnDef<AuditLogItem>[] = [
  {
    accessorKey: "occurred_at",
    header: "Timestamp",
    cell: ({ row }) => (
      <span className="whitespace-nowrap font-mono text-xs text-zinc-600 dark:text-zinc-400">
        {formatTimestamp(row.original.occurred_at)}
      </span>
    ),
  },
  {
    accessorKey: "event_type",
    header: "Event Type",
    cell: ({ row }) => (
      <Badge variant="secondary" className="font-mono text-xs">
        {row.original.event_type}
      </Badge>
    ),
  },
  {
    accessorKey: "actor",
    header: "Actor",
    cell: ({ row }) => {
      const actor = row.original.actor;
      if (!actor) return <span className="text-zinc-400">—</span>;
      if (actor.length <= 20) {
        return <span className="text-zinc-600 dark:text-zinc-400">{actor}</span>;
      }
      return (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="cursor-default text-zinc-600 dark:text-zinc-400">
              {truncate(actor, 20)}
            </span>
          </TooltipTrigger>
          <TooltipContent>{actor}</TooltipContent>
        </Tooltip>
      );
    },
  },
  {
    id: "payload",
    header: "Payload",
    cell: ({ row }) => (
      <div className="max-w-md">
        <AuditPayloadViewer payload={row.original.payload} />
      </div>
    ),
  },
];

export function AuditLogTable({
  initialData,
  eventTypes,
}: {
  initialData: PaginatedResponse<AuditLogItem>;
  eventTypes: string[];
}) {
  const [data, setData] =
    React.useState<PaginatedResponse<AuditLogItem>>(initialData);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(false);

  // Filter state.
  const [eventType, setEventType] = React.useState<string>("");
  const [actor, setActor] = React.useState("");
  const [dateRange, setDateRange] = React.useState<DateRange>({
    from: "",
    to: "",
  });
  const [page, setPage] = React.useState(1);

  // Skip the very first fetch — the server component already provided page 1.
  const firstRender = React.useRef(true);

  const currentFilters: AuditLogParams = React.useMemo(
    () => ({
      event_type: eventType || undefined,
      actor: actor || undefined,
      date_from: dateRange.from ? `${dateRange.from}T00:00:00Z` : undefined,
      date_to: dateRange.to ? `${dateRange.to}T23:59:59Z` : undefined,
    }),
    [eventType, actor, dateRange],
  );

  React.useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(false);
    fetchAuditLog({ ...currentFilters, page, page_size: PAGE_SIZE })
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
    manualPagination: true,
    manualSorting: true,
    rowCount: data.total,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex flex-col gap-6">
        {/* Filter bar */}
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex flex-col gap-1">
            <span className="text-xs font-medium text-zinc-500">Event type</span>
            <Select
              value={eventType === "" ? EVENT_ALL : eventType}
              onValueChange={(v) => {
                setEventType(v === EVENT_ALL ? "" : v);
                resetToFirstPage();
              }}
            >
              <SelectTrigger
                className="w-[220px]"
                aria-label="Filter by event type"
              >
                <SelectValue placeholder="All events" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={EVENT_ALL}>All events</SelectItem>
                {eventTypes.map((et) => (
                  <SelectItem key={et} value={et}>
                    {et}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <AdminSearchInput
            value={actor}
            onChange={(v) => {
              setActor(v);
              resetToFirstPage();
            }}
            placeholder="Search by actor..."
            ariaLabel="Search audit log by actor"
          />
          <DateRangeFilter
            value={dateRange}
            onChange={(v) => {
              setDateRange(v);
              resetToFirstPage();
            }}
          />
        </div>

        {/* Table */}
        <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
          <Table>
            <TableHeader className="bg-zinc-50 dark:bg-zinc-900">
              {table.getHeaderGroups().map((hg) => (
                <TableRow key={hg.id}>
                  {hg.headers.map((header) => (
                    <TableHead key={header.id}>
                      {flexRender(
                        header.column.columnDef.header,
                        header.getContext(),
                      )}
                    </TableHead>
                  ))}
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
                      No audit entries
                    </p>
                    <p className="mt-1 text-sm text-zinc-500">
                      No audit log entries match your filters. Try broadening the
                      date range or event type.
                    </p>
                  </TableCell>
                </TableRow>
              ) : (
                table.getRowModel().rows.map((row) => (
                  <TableRow key={row.id} className="align-top">
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
