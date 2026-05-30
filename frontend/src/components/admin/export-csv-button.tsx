/**
 * Plan 08-03 — CSV export dropdown.
 *
 * `outline` "Export" button + DropdownMenu with 3 items (Users / Transactions
 * / Bets). Each item calls the `adminApiExport` Server Action with the current
 * user-list filters (so the export matches the filtered view per D-08), turns
 * the returned CSV text into a Blob, and triggers a browser download. Shows a
 * spinner while exporting and toasts "Export started" via sonner.
 */
"use client";

import * as React from "react";
import { Download, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { adminApiExport } from "@/lib/admin-api";
import { buildUsersQuery } from "@/lib/admin-query";
import type { UserListParams } from "@/lib/admin-types";

type ExportKind = "users" | "transactions" | "bets";

const LABELS: Record<ExportKind, string> = {
  users: "Export Users (CSV)",
  transactions: "Export Transactions (CSV)",
  bets: "Export Bets (CSV)",
};

export function ExportCsvButton({ filters }: { filters: UserListParams }) {
  const [exporting, setExporting] = React.useState(false);

  async function handleExport(kind: ExportKind) {
    if (exporting) return;
    setExporting(true);
    toast("Export started. Your download will begin shortly.");
    try {
      // Export the current filtered view (page/size are list-only; the export
      // is the full filtered set, capped server-side at 10k rows — D-10).
      const qs = buildUsersQuery({
        search: filters.search,
        status: filters.status,
        signup_after: filters.signup_after,
        signup_before: filters.signup_before,
        sort_by: filters.sort_by,
        sort_order: filters.sort_order,
      });
      const { csv, filename } = await adminApiExport(
        `/api/v1/admin/export/${kind}${qs}`,
      );
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename || `${kind}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Export failed. Please try again.");
    } finally {
      setExporting(false);
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" disabled={exporting}>
          {exporting ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Download className="h-4 w-4" aria-hidden="true" />
          )}
          Export
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {(Object.keys(LABELS) as ExportKind[]).map((kind) => (
          <DropdownMenuItem
            key={kind}
            onSelect={(e) => {
              // Keep the menu's default close behaviour but run our async work.
              e.preventDefault();
              void handleExport(kind);
            }}
          >
            {LABELS[kind]}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
