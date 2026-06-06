/**
 * Home page — the curated catalog browse (Phase 17).
 *
 * Upgraded from the plain market list (`GET /markets`) to the curated catalog
 * (`GET /catalog`): an async Server Component that reads the URL `searchParams`,
 * fetches the catalog + categories server-side (`cache:"no-store"`, fresh per
 * render), and renders the client filter controls + a grid mixing the binary
 * `MarketCard` (`type:"market"`, via the adapter) and the distinct `EventCard`
 * (`type:"event"`). Every zero-result filter combination shows an explicit empty
 * state, never an error (BRW-05). The route `loading.tsx` provides the skeleton.
 */
import { MarketCard } from "@/components/market-card";
import { MarketGrid } from "@/components/market-grid";
import { EventCard } from "@/components/catalog/event-card";
import { CatalogControls } from "@/components/catalog/catalog-controls";
import {
  fetchCatalog,
  fetchCategories,
  catalogMarketToMarketItem,
  type CatalogItem,
  type PublicCatalogStatus,
  type CatalogSort,
} from "@/lib/catalog";

const PAGE_SHELL = "w-full max-w-6xl mx-auto px-4 sm:px-6 py-12";

interface HomeSearchParams {
  q?: string;
  category?: string;
  status?: string;
  sort?: string;
}

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<HomeSearchParams>;
}) {
  const sp = await searchParams;

  // Categories degrade to [] (the chip row just hides); the catalog is the gate.
  const [categoriesResult, catalogResult] = await Promise.allSettled([
    fetchCategories(),
    fetchCatalog({
      q: sp.q,
      category: sp.category,
      status: sp.status as PublicCatalogStatus | undefined,
      sort: sp.sort as CatalogSort | undefined,
    }),
  ]);

  const categories =
    categoriesResult.status === "fulfilled" ? categoriesResult.value : [];

  return (
    <main className={PAGE_SHELL}>
      <h1 className="mb-8 text-xl font-semibold">Markets</h1>

      <CatalogControls
        categories={categories}
        q={sp.q}
        category={sp.category}
        status={sp.status}
        sort={sp.sort}
      />

      {catalogResult.status === "rejected" ? (
        <CatalogError />
      ) : catalogResult.value.length === 0 ? (
        <CatalogEmpty />
      ) : (
        <MarketGrid>
          {catalogResult.value.map((item: CatalogItem) =>
            item.type === "event" ? (
              <EventCard key={item.id} event={item} />
            ) : (
              <MarketCard
                key={item.id}
                market={catalogMarketToMarketItem(item)}
              />
            ),
          )}
        </MarketGrid>
      )}
    </main>
  );
}

/** Explicit empty state for any zero-result filter combination (BRW-05). */
function CatalogEmpty() {
  return (
    <div
      className="flex flex-col items-center justify-center py-24 text-center"
      role="status"
    >
      <h2 className="text-lg font-semibold">No markets found</h2>
      <p className="mt-2 text-sm text-zinc-500">
        No markets match your current filters. Try adjusting the search or filter
        criteria.
      </p>
    </div>
  );
}

/** Catalog fetch failure (distinct from an empty result). */
function CatalogError() {
  return (
    <div
      className="flex flex-col items-center justify-center py-24 text-center"
      role="status"
    >
      <h2 className="text-lg font-semibold text-rose-700">
        Failed to load markets
      </h2>
      <p className="mt-2 text-sm text-zinc-500">
        Something went wrong while loading the catalog. Please try again.
      </p>
    </div>
  );
}
