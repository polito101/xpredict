/**
 * Plan 12-06 — Admin market detail page (Surface 3 host: edit + settlement).
 *
 * Server Component (`dynamic = "force-dynamic"`): fetches the market via the
 * `fetchMarketAdmin` Server Action (Bearer-forwarded admin_jwt) and hands it to
 * the `MarketDetailActions` client island. Mirrors the shipped
 * `/admin/users/[id]/page.tsx` detail-page-hosts-actions convention — the static
 * "Back to markets" link + the question header live in this server shell; the
 * `MarketForm` (edit-mode) and the status/source-gated settlement/close action
 * buttons + dialogs live in the island.
 *
 * The island hosts the four gated actions (UI-SPEC §Surface 3):
 *   - Resolve            → ResolveMarketDialog      (OPEN/CLOSED house)
 *   - Force-settle       → ForceSettleDialog        (OPEN/CLOSED Polymarket)
 *   - Reverse settlement → ReverseSettlementDialog  (RESOLVED)
 *   - Close market       → CloseMarketDialog        (OPEN)
 * and the shared 12-05 `MarketForm` in edit-mode (criteria locks when bet_count > 0).
 *
 * If the fetch fails (404 / expired session) we render the UI-SPEC error block
 * instead of crashing (mirrors admin/users/[id]/page.tsx).
 *
 * Next.js 16: route `params` is async — it is awaited before use.
 * Layout per UI-SPEC: `max-w-6xl mx-auto px-6 py-12`.
 */
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { MarketDetailActions } from "@/components/admin/market-detail-actions";
import { MarketStatusBadge } from "@/components/admin/market-status-badge";
import { SourceBadge } from "@/components/source-badge";
import { fetchMarketAdmin } from "@/lib/admin-markets-api";
import type { MarketDetail } from "@/lib/admin-markets-types";

export const dynamic = "force-dynamic";

export default async function AdminMarketDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let market: MarketDetail | null = null;
  try {
    market = await fetchMarketAdmin(id);
  } catch {
    market = null;
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <Link
        href="/admin/markets"
        className="mb-8 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to markets
      </Link>

      {market ? (
        <>
          <header className="mb-8 flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-semibold tracking-tight">
              {market.question}
            </h1>
            <SourceBadge source={market.source} sourceUrl={null} />
            <MarketStatusBadge status={market.status} />
          </header>

          <MarketDetailActions market={market} />
        </>
      ) : (
        <div className="py-12 text-center">
          <p className="text-sm font-medium text-red-400">
            Failed to load data
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Something went wrong while loading this page. Please try again.
          </p>
        </div>
      )}
    </div>
  );
}
