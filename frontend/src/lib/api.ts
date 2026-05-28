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

// -- Fetch helpers -----------------------------------------------------------

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Fetches the public market list from the backend.
 * Uses `cache: "no-store"` for Server Component (fresh on every render).
 */
export async function fetchMarkets(): Promise<MarketItem[]> {
  const res = await fetch(`${API_BASE}/api/v1/markets`, {
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch markets: ${res.status}`);
  }

  return res.json() as Promise<MarketItem[]>;
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
