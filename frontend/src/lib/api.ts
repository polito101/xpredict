/**
 * API types and fetch helpers for the XPredict backend.
 *
 * Types match the backend response shape from /api/v1/markets.
 */

import { SESSION_COOKIE_NAME } from "./config";

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
 * `MarketRead` returns `resolution_criteria` alongside the list fields, plus —
 * after Plan 12-01 — the resolution projection (`winning_outcome_id` /
 * `resolution_source` / `resolution_justification` / `resolved_at`) and the
 * per-market stake bounds (`min_stake` / `max_stake`).
 *
 * The resolution fields are non-null only once a market is RESOLVED; before
 * that the backend serializes them as `null`. `fetchMarket` keeps its 404 logic
 * unchanged — Plan 12-01 stopped 404ing RESOLVED markets, so a resolved slug now
 * returns 200 carrying this shape (the player resolution panel reads it).
 *
 * Money is a STRING on the wire (`Numeric(18,4)` serialized as a string — SP-1);
 * `min_stake`/`max_stake` are `string | null` (NULL = the platform default) and
 * are consumed by the order-form per-market bounds (BET-06 / Plan 12-03).
 */
export interface MarketDetail extends MarketItem {
  resolution_criteria: string;
  winning_outcome_id: string | null;
  resolution_source: string | null;
  resolution_justification: string | null;
  resolved_at: string | null;
  min_stake: string | null;
  max_stake: string | null;
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

// -- Live-bets types (LB-B) --------------------------------------------------

/**
 * The minted live-bets session (`POST /api/live/session`). Matches LB-A
 * `SessionResponse` (`backend/app/integrations/livebets/schemas.py`): a
 * short-lived per-player JWT (`session_token`) the widget is rendered with, its
 * `expires_at`, and the `table_id` the session was minted for (all STRINGS on the
 * wire — design §7).
 *
 * `table_id` is the demo's source of the widget's `table-id` attribute: the
 * live-bets `GET /tables` route is JWT-gated, so the operator-key
 * `/api/live/tables` can't list tables — LB-A echoes the resolved id here instead.
 */
export interface LiveSession {
  session_token: string;
  expires_at: string;
  table_id: string;
}

/**
 * One live-bets catalog table (`GET /api/live/tables`). Matches LB-A
 * `TableItem`; `name` is optional server-side, so it is `string | null` here.
 * The `table_id` feeds the widget's `table-id` attribute (design §5).
 */
export interface LiveTable {
  table_id: string;
  name: string | null;
}

/**
 * The placed/settled mirror outcome. Matches LB-A `MirrorResult`. `applied`
 * is `false` for an idempotent no-op (the bet was already mirrored / already
 * settled) — a benign success, NOT an error (design §8 idempotency). `status`
 * stays a string (the live-bets bet status echoed back by LB-A).
 */
export interface LiveMirrorResult {
  bet_id: string;
  status: string;
  applied: boolean;
}

/**
 * Thrown by `fetchLiveSession` when LB-A returns 400 ("No table_id supplied and
 * LIVEBETS_DEFAULT_TABLE_ID is not configured."). Lets the `/live` page branch
 * to the friendly "No live table configured yet" empty state — the default
 * LB-B demo state before LB-C ships a table — instead of a generic error
 * (CONTEXT Scope-IN bullet 1). Mirrors `MarketNotFound`.
 */
export class LiveTableUnconfigured extends Error {
  constructor() {
    super("No live table configured (LIVEBETS_DEFAULT_TABLE_ID is unset).");
    this.name = "LiveTableUnconfigured";
  }
}

/**
 * Mints (or renews) the player's live-bets session via LB-A
 * `POST /api/live/session`. Runs SERVER-SIDE from the `/live` Server Component,
 * so it takes the player's HttpOnly `xpredict_session` cookie value and forwards
 * it as a `Cookie:` header — the cookie is HttpOnly and the backend is a
 * different origin, so `credentials:"include"` would not carry it (mirrors
 * `bet-actions.ts` / `wallet/page.tsx`). The body sends `{ table_id }` only when
 * supplied; otherwise LB-A defaults from `LIVEBETS_DEFAULT_TABLE_ID`. A 400
 * (no table configured) throws `LiveTableUnconfigured`; any other non-ok throws
 * `Error` with the status. Uses `apiBase()` + `no-store` (mirrors `fetchMarket`).
 *
 * The 200 body carries `table_id` (the table the session was minted for) — the
 * `/live` page feeds it straight into the widget's `table-id` attribute, so there
 * is no need to call the (JWT-gated, operator-key-incompatible) `/api/live/tables`.
 */
export async function fetchLiveSession(
  session: string,
  tableId?: string,
): Promise<LiveSession> {
  const res = await fetch(`${apiBase()}/api/live/session`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Cookie: `${SESSION_COOKIE_NAME}=${session}`,
    },
    // SessionRequest accepts an optional table_id; omit the key when undefined
    // so LB-A falls back to LIVEBETS_DEFAULT_TABLE_ID.
    body: JSON.stringify(tableId === undefined ? {} : { table_id: tableId }),
    cache: "no-store",
  });

  if (res.status === 400) {
    throw new LiveTableUnconfigured();
  }
  if (!res.ok) {
    throw new Error(`Failed to mint live session: ${res.status}`);
  }

  return res.json() as Promise<LiveSession>;
}

/**
 * Lists the live-bets catalog tables via LB-A `GET /api/live/tables`. Runs
 * SERVER-SIDE; forwards the player's session cookie exactly like
 * `fetchLiveSession`. Reads the `.tables` array off LB-A `TablesResponse`. Uses
 * `apiBase()` + `no-store`.
 *
 * NOTE: this is NOT on the demo path. The underlying live-bets `GET /tables` is
 * JWT-gated (player session), but XPredict's `/api/live/tables` calls it with the
 * operator key, which 401s — so this cannot resolve the demo table id. The widget
 * now gets its `table-id` from the session's `table_id` (see `fetchLiveSession` /
 * LB-A `SessionResponse`). Left in place for a future JWT-forwarding path.
 */
export async function fetchLiveTables(session: string): Promise<LiveTable[]> {
  const res = await fetch(`${apiBase()}/api/live/tables`, {
    headers: { Cookie: `${SESSION_COOKIE_NAME}=${session}` },
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch live tables: ${res.status}`);
  }

  const data = (await res.json()) as { tables?: LiveTable[] };
  return data.tables ?? [];
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
