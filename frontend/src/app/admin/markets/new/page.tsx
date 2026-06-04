/**
 * Plan 12-05 — Admin "create market" route (ADM-02).
 *
 * Renders the shared `MarketForm` in create-mode inside the standard admin page
 * shell. On success the form navigates (router.push) to the new market's detail
 * page (or the list). The detail/edit host (`[id]/page.tsx`) lands in 12-06.
 *
 * Layout per UI-SPEC §Surface 2: `max-w-6xl mx-auto px-6 py-12`, H1.
 */
import { MarketForm } from "@/components/admin/market-form";

export const dynamic = "force-dynamic";

export default function NewMarketPage() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <h1 className="mb-8 text-xl font-semibold tracking-tight">
        Create market
      </h1>
      <MarketForm mode="create" />
    </div>
  );
}
