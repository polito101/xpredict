/**
 * Plan 12-05 — Admin markets list page (ADM-01, BLOCKER-3).
 *
 * Server Component: does the initial page-1 fetch via the `fetchMarkets` Server
 * Action (Bearer-forwarded admin_jwt) and hands the data to the client-side
 * `MarketsDataTable`. If the initial load fails (e.g. the admin session
 * expired), it degrades to an empty table rather than crashing — the table's
 * own error state covers subsequent refetch failures.
 *
 * Clone of `admin/users/page.tsx`; adds a top-right primary "Create market"
 * Button linking to the create route (`/admin/markets/new`, Task 2).
 *
 * Layout per UI-SPEC §Surface 2: `max-w-6xl mx-auto px-6 py-12`, H1 "Markets".
 */
import Link from "next/link";

import { MarketsDataTable } from "@/components/admin/markets-data-table";
import { Button } from "@/components/ui/button";
import { fetchMarkets } from "@/lib/admin-markets-api";
import type {
  PaginatedResponse,
  MarketListItem,
} from "@/lib/admin-markets-types";

export const dynamic = "force-dynamic";

export default async function AdminMarketsPage() {
  let initialData: PaginatedResponse<MarketListItem>;
  try {
    initialData = await fetchMarkets({
      page: 1,
      page_size: 20,
      sort_by: "created_at",
      sort_order: "desc",
    });
  } catch {
    initialData = { items: [], total: 0, page: 1, page_size: 20, pages: 1 };
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <div className="mb-8 flex items-center justify-between gap-4">
        <h1 className="text-xl font-semibold tracking-tight">Markets</h1>
        <Button asChild>
          <Link href="/admin/markets/new">Create market</Link>
        </Button>
      </div>
      <MarketsDataTable initialData={initialData} />
    </div>
  );
}
