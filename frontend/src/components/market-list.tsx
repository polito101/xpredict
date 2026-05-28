/**
 * MarketList -- async Server Component that fetches and renders the market grid.
 *
 * Handles empty, error, and populated states.
 */
import { MarketCard } from "@/components/market-card";
import { fetchMarkets } from "@/lib/api";

export default async function MarketList() {
  let markets;

  try {
    markets = await fetchMarkets();
  } catch {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center" role="status">
        <h2 className="text-lg font-semibold text-rose-700">
          Unable to load markets
        </h2>
        <p className="mt-2 text-sm text-zinc-500">
          Something went wrong while fetching markets. Try refreshing the page.
        </p>
      </div>
    );
  }

  if (markets.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center" role="status">
        <h2 className="text-lg font-semibold">
          No markets yet
        </h2>
        <p className="mt-2 text-sm text-zinc-500">
          Markets will appear here once they are created or synced. Check back soon.
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {markets.map((market) => (
        <MarketCard key={market.id} market={market} />
      ))}
    </div>
  );
}
