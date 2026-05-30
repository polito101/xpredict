/**
 * API types and fetch helpers for the XPredict backend.
 *
 * Types match the backend response shape from /api/v1/markets.
 */

// -- Types ------------------------------------------------------------------

export interface MarketOutcome {
  id: string;
  label: string;
  initial_odds: string;
  current_odds: string;
}

export interface MarketItem {
  id: string;
  question: string;
  slug: string;
  category: string | null;
  source: string;
  source_market_id: string | null;
  status: string;
  deadline: string;
  bet_count: number;
  created_at: string;
  volume: string;
  volume_24hr: string;
  source_url: string | null;
  outcomes: MarketOutcome[];
}

/**
 * A single YES-probability snapshot for the price-history chart.
 *
 * `probability` is a string on the wire (backend `Numeric(8,6)` serialized as
 * a string — the project's money/odds-as-string convention). Only round it
 * for display; never store it as a float.
 */
export interface PricePoint {
  ts: string;
  probability: string;
}

/** Chart window options for the price-history chart (default `7d`). */
export type PriceWindow = "24h" | "7d" | "30d";

/**
 * The market-detail payload (`GET /api/v1/markets/{slug}`). The backend
 * `MarketRead` already returns `resolution_criteria` alongside the list fields.
 */
export interface MarketDetail extends MarketItem {
  resolution_criteria: string;
}

/** The price-history endpoint response (`GET .../price-history?window=`). */
export interface PriceHistoryResponse {
  window: PriceWindow;
  points: PricePoint[];
}

/**
 * A single recent-activity row (`GET .../activity`). Fully anonymized
 * server-side — there is intentionally NO user identity field. `amount` is a
 * string on the wire (money is `Numeric(18,4)` serialized as a string — SP-1).
 */
export interface ActivityItem {
  outcome: "YES" | "NO";
  amount: string;
  created_at: string;
}

// -- Fetch helpers -----------------------------------------------------------

/**
 * Resolves the backend base URL for the current execution context.
 *
 * Server-side (SSR / Server Components) reaches the backend over the internal
 * network — in Docker that is `BACKEND_URL` (e.g. `http://backend:8000`). The
 * browser must use the public, host-reachable URL from `NEXT_PUBLIC_API_URL`
 * (e.g. `http://localhost:8000`). Conflating the two left the client-side
 * price-history re-fetch (and, mirrored in `use-market-socket`, the WS base)
 * pointing at the unresolvable `backend` hostname under the dockerized
 * `bin/dev` stack — the browser cannot resolve a Docker-internal hostname
 * (Phase 9 closeout finding). Both fall back to localhost for host-run dev.
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
 * Fetches the public market list from the backend.
 * Uses `cache: "no-store"` for Server Component (fresh on every render).
 */
export async function fetchMarkets(): Promise<MarketItem[]> {
  const res = await fetch(`${apiBase()}/api/v1/markets`, {
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch markets: ${res.status}`);
  }

  return res.json() as Promise<MarketItem[]>;
}

/**
 * Thrown by `fetchMarket` when the backend returns 404, so the detail page can
 * render the "Market not found" state distinctly from a generic fetch error
 * (RESEARCH Pattern 6).
 */
export class MarketNotFound extends Error {
  constructor(slug: string) {
    super(`Market not found: ${slug}`);
    this.name = "MarketNotFound";
  }
}

/**
 * Fetches a single market's detail payload by slug. Mirrors `fetchMarkets`
 * (`cache: "no-store"` for the Server Component initial render). Throws a typed
 * `MarketNotFound` on 404 so the page can branch to the not-found state.
 */
export async function fetchMarket(slug: string): Promise<MarketDetail> {
  const res = await fetch(
    `${apiBase()}/api/v1/markets/${encodeURIComponent(slug)}`,
    { cache: "no-store" },
  );

  if (res.status === 404) {
    throw new MarketNotFound(slug);
  }
  if (!res.ok) {
    throw new Error(`Failed to fetch market: ${res.status}`);
  }

  return res.json() as Promise<MarketDetail>;
}

/**
 * Fetches downsampled YES price history for a market over the given window
 * (`24h` | `7d` | `30d`, default `7d`). Server-side downsampling keeps the 30d
 * view light (RESEARCH Pattern 5).
 */
export async function fetchPriceHistory(
  slug: string,
  window: PriceWindow = "7d",
): Promise<PriceHistoryResponse> {
  const res = await fetch(
    `${apiBase()}/api/v1/markets/${encodeURIComponent(slug)}/price-history?window=${window}`,
    { cache: "no-store" },
  );

  if (!res.ok) {
    throw new Error(`Failed to fetch price history: ${res.status}`);
  }

  return res.json() as Promise<PriceHistoryResponse>;
}

/**
 * Fetches the anonymized recent-activity feed (last 20 bets) for a market.
 * The backend strips all user identity server-side (RESEARCH Pattern 8).
 */
export async function fetchActivity(slug: string): Promise<ActivityItem[]> {
  const res = await fetch(
    `${apiBase()}/api/v1/markets/${encodeURIComponent(slug)}/activity`,
    { cache: "no-store" },
  );

  if (!res.ok) {
    throw new Error(`Failed to fetch activity: ${res.status}`);
  }

  return res.json() as Promise<ActivityItem[]>;
}

// -- Format helpers ----------------------------------------------------------

/**
 * Converts a Decimal string volume to a compact display string.
 *
 * >= 1_000_000 -> "$X.XM"
 * >= 1_000     -> "$X.XK"  (only shows decimal if < 100K, e.g. "$1.5K" but "$450K")
 * < 1_000      -> "$XXX"
 */
export function formatVolume(volume: string): string {
  const num = parseFloat(volume);

  if (Number.isNaN(num)) return "$0";

  if (num >= 1_000_000) {
    const millions = num / 1_000_000;
    return `$${millions % 1 === 0 ? millions.toFixed(0) : millions.toFixed(1)}M`;
  }

  if (num >= 1_000) {
    const thousands = num / 1_000;
    if (thousands >= 100) {
      return `$${Math.round(thousands)}K`;
    }
    return `$${thousands % 1 === 0 ? thousands.toFixed(0) : thousands.toFixed(1)}K`;
  }

  return `$${Math.round(num)}`;
}

/**
 * Formats a deadline ISO string for display.
 * Uses Intl.DateTimeFormat with short month, numeric day, numeric year.
 * Returns "Ended" if the date is in the past.
 */
export function formatDeadline(deadline: string): string {
  const date = new Date(deadline);

  if (Number.isNaN(date.getTime())) return "No deadline";

  if (date < new Date()) {
    return "Ended";
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}
