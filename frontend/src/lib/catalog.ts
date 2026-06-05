/**
 * Catalog API types + fetch helpers (Phase 17).
 *
 * Mirrors `lib/api.ts`: the same `apiBase()` server/browser split, every read
 * uses `cache: "no-store"` (fresh per Server-Component render), and a typed
 * `EventNotFound` throw (cf. `MarketNotFound`) so the event page can branch to a
 * distinct not-found state. Consumes the merged Phase-16 contract:
 *   GET /api/v1/catalog?q&category&status&sort  -> CatalogItem[] (bounded LIMIT 100)
 *   GET /api/v1/events/{slug}                    -> EventDetail (404 if <2 children)
 *   GET /api/v1/categories                       -> string[] (non-empty only)
 *
 * Money/odds (`yes_price`, `volume`) are STRINGS on the wire (Numeric serialized
 * as a string — the project SP-1 convention); only round for display.
 */
import type { MarketItem } from "@/lib/api";

// -- Types ------------------------------------------------------------------

/** Public catalog status vocabulary (the 3-value filter set). */
export type PublicCatalogStatus = "open" | "closing_soon" | "resolved";
/** Catalog sort vocabulary (default "volume"). */
export type CatalogSort = "volume" | "closing_soonest" | "newest";
/** The richer 4-value derived status surfaced on the event detail. */
export type EventDerivedStatus =
  | "open"
  | "partially_resolved"
  | "resolved"
  | "void";

/** One outcome on a catalog item (1 row for a market, N for an event). */
export interface CatalogOutcome {
  label: string;
  yes_outcome_id: string | null;
  yes_price: string;
}

/** A catalog grid item — discriminated on `type` (standalone market vs event). */
export interface CatalogItem {
  type: "market" | "event";
  id: string;
  slug: string;
  title: string;
  category: string | null;
  source: string;
  status: PublicCatalogStatus;
  deadline: string | null;
  volume: string;
  created_at: string;
  outcomes: CatalogOutcome[];
}

/** One child (outcome) row on the event detail — carries the bet/chart seams. */
export interface EventOutcomeRead {
  label: string;
  yes_outcome_id: string | null;
  yes_price: string;
  market_id: string;
  child_slug: string;
  child_status: string;
}

/** The event-detail payload (`GET /api/v1/events/{slug}`). */
export interface EventDetail {
  id: string;
  slug: string;
  title: string;
  category: string | null;
  source: string;
  status: EventDerivedStatus;
  deadline: string | null;
  created_at: string;
  outcomes: EventOutcomeRead[];
}

/** Browse filter inputs (all optional; omitted = no filter). */
export interface CatalogQuery {
  q?: string;
  category?: string;
  status?: PublicCatalogStatus;
  sort?: CatalogSort;
}

// -- Fetch helpers -----------------------------------------------------------

/**
 * Backend base for the current execution context (identical to `lib/api.ts`):
 * server-side → `BACKEND_URL` (Docker-internal) → `NEXT_PUBLIC_API_URL` → localhost;
 * browser → `NEXT_PUBLIC_API_URL` → localhost. The split is load-bearing under
 * the dockerized dev stack (a browser can't resolve the `backend` hostname).
 */
function apiBase(): string {
  if (typeof window === "undefined") {
    return (
      process.env.BACKEND_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "http://localhost:8000"
    );
  }
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

/**
 * Fetches the curated catalog. Builds the query string from the non-empty
 * filters only (an absent filter is simply omitted). Bounded server-side to 100
 * items; every filter combination returns a (possibly empty) array, never an
 * error. Local pg_trgm search only — never proxied to Gamma.
 */
export async function fetchCatalog(
  params: CatalogQuery = {},
): Promise<CatalogItem[]> {
  const sp = new URLSearchParams();
  if (params.q) sp.set("q", params.q);
  if (params.category) sp.set("category", params.category);
  if (params.status) sp.set("status", params.status);
  if (params.sort) sp.set("sort", params.sort);
  const qs = sp.toString();
  const res = await fetch(`${apiBase()}/api/v1/catalog${qs ? `?${qs}` : ""}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch catalog: ${res.status}`);
  }
  return res.json() as Promise<CatalogItem[]>;
}

/**
 * Thrown by `fetchEvent` on a 404 so the event page can render the "Event not
 * found" state distinctly from a generic fetch error (mirrors `MarketNotFound`).
 * The backend 404s a missing slug AND a single-outcome group (EVT-07: 1-child
 * events stay on `/markets/{slug}`).
 */
export class EventNotFound extends Error {
  constructor(slug: string) {
    super(`Event not found: ${slug}`);
    this.name = "EventNotFound";
  }
}

/** Fetches a multi-outcome event by slug. Throws `EventNotFound` on 404. */
export async function fetchEvent(slug: string): Promise<EventDetail> {
  const res = await fetch(
    `${apiBase()}/api/v1/events/${encodeURIComponent(slug)}`,
    { cache: "no-store" },
  );
  if (res.status === 404) {
    throw new EventNotFound(slug);
  }
  if (!res.ok) {
    throw new Error(`Failed to fetch event: ${res.status}`);
  }
  return res.json() as Promise<EventDetail>;
}

/** Fetches the non-empty category names (sorted DISTINCT union; CAT-06). */
export async function fetchCategories(): Promise<string[]> {
  const res = await fetch(`${apiBase()}/api/v1/categories`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch categories: ${res.status}`);
  }
  return res.json() as Promise<string[]>;
}

// -- Adapter -----------------------------------------------------------------

/**
 * Adapts a `type:"market"` `CatalogItem` to the `MarketItem` shape the existing
 * binary `MarketCard` consumes, so the catalog grid reuses that card verbatim.
 *
 * `deadline ?? ""` is load-bearing: the catalog deadline can be null, and
 * `formatDeadline(new Date(""))` → "No deadline", whereas `new Date(null)` →
 * the 1970 epoch → "Ended" (wrong). The synthetic NO outcome is intentionally
 * absent — `MarketCard` derives the NO percent as the YES complement and never
 * needs a NO id (only the bet path does, which the catalog card never offers).
 */
export function catalogMarketToMarketItem(item: CatalogItem): MarketItem {
  return {
    id: item.id,
    question: item.title,
    slug: item.slug,
    category: item.category,
    source: item.source,
    source_market_id: null,
    status: item.status,
    deadline: item.deadline ?? "",
    bet_count: 0,
    created_at: item.created_at,
    volume: item.volume,
    volume_24hr: "0",
    source_url: null,
    outcomes: item.outcomes.map((o) => ({
      id: o.yes_outcome_id ?? "",
      label: o.label,
      initial_odds: o.yes_price,
      current_odds: o.yes_price,
    })),
  };
}
