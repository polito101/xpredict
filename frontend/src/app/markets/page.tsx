/**
 * Markets — the app's curated catalog browse (Phase 17 content, relocated here
 * in Phase 19 when `/` became the public brand landing).
 *
 * An async Server Component (behind auth — the edge middleware gates `/markets`):
 * reads the URL `searchParams`, fetches the catalog + categories server-side
 * (`cache:"no-store"`, fresh per render), and renders the client filter controls
 * + a grid mixing the binary `MarketCard` (`type:"market"`, via the adapter) and
 * the distinct `EventCard` (`type:"event"`). Every zero-result filter combination
 * shows an explicit empty state, never an error (BRW-05).
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

const PAGE_SHELL = "w-full max-w-6xl mx-auto px-4 sm:px-6 py-10";

interface MarketsSearchParams {
  q?: string;
  category?: string;
  status?: string;
  sort?: string;
}

export default async function MarketsPage({
  searchParams,
}: {
  searchParams: Promise<MarketsSearchParams>;
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
  const count =
    catalogResult.status === "fulfilled" ? catalogResult.value.length : 0;

  return (
    <main className={PAGE_SHELL}>
      <div className="mb-8 flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="font-display text-3xl font-semibold tracking-tight">
          Markets
        </h1>
        {catalogResult.status === "fulfilled" && count > 0 && (
          <span className="text-sm text-muted-foreground">
            {count} {count === 1 ? "market" : "markets"}
          </span>
        )}
      </div>

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
      className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border py-24 text-center"
      role="status"
    >
      <h2 className="text-lg font-semibold">No markets found</h2>
      <p className="mt-2 max-w-sm text-sm text-muted-foreground">
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
      className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border py-24 text-center"
      role="status"
    >
      <h2 className="text-lg font-semibold text-red-400">
        Failed to load markets
      </h2>
      <p className="mt-2 max-w-sm text-sm text-muted-foreground">
        Something went wrong while loading the catalog. Please try again.
      </p>
    </div>
  );
}
